from BeautifulSoup import BeautifulSoup, Tag
import urllib
import urllib2
import csv
import os
import re
import json
from collections import OrderedDict
import tldextract
import logging
import unicodedata
from StringIO import StringIO
import gzip
from weasyprint import HTML, CSS
from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.colors import orange
from text.classifiers import NaiveBayesClassifier

class Extractor:
   input_csv_filename = ""
    
   classifiers = {}
   yes_words_dict = {}
   click_words = []

   yes_words_csv = None # a file object for the csv
   yes_words_pdf = "" # the filename for the pdf
   bayes_csv = None # a file object for the csv
   bayes_pdf = "" # the filename for the pdf
    
   def __init__(self, input_csv_filename, yes_words_csv_filename, click_strings, categorized_text_filename):
       #process input
       #csvfile = open(input_csv, 'rb')
       #input_reader = csv.reader(csvfile, delimiter=',')
       self.input_csv_filename = input_csv_filename

       #process yes_words
       self.yes_words_dict = self.processYesWords(yes_words_csv_filename)

       #process click_strings
       self.click_words = self.processClickStrings(click_strings)

       #process categorized data
       #self.classifiers = self.processTextData(categorized_text_filename)

   '''
   Input processing
   '''

   def processTextData(self, filename):
       f = open(filename, 'r')
       column_names_str = f.readline()
       str = re.search('\[(.*)\]',column_names_str)
       column_names = str.group(1).split(",")
       #print column_names

       training_data = {}
       for key in column_names:
           training_data[key] = []

       whole_str = f.read()
       passages = whole_str.split("*DELIM*")
       passages = passages[1:]
       for passage in passages:
           columns_str = re.search('\[(.*)\]',passage)
           columns = columns_str.group(1).split(",")
           #print columns
           i = passage.find("]")
           classify_str = passage[i+1:]
           for i in range(len(columns)):
               column = columns[i]
               if column == "*":
                   training_data[column_names[i]].append((classify_str,'pos'))
               else:
                   training_data[column_names[i]].append((classify_str,'neg'))

       global classifiers
       classifiers = {}
       for key in training_data:
           classifiers[key] = NaiveBayesClassifier(training_data[key])
       return classifiers

   def processClickStrings(self,click_strings):
       click_words = []
       for string in click_strings:
           new_words =  re.split('[\W^_]+',string)
           for word in new_words:
               word_lower = word.lower()
               if (not word_lower in click_words):
                   click_words.append(word_lower)
       return click_words

   def processYesWords(self,yes_words_csv): 
       csvfile = open(yes_words_csv, 'rb')
       yes_words_reader = csv.reader(csvfile, delimiter=',')
       yes_words_dict = {}
       done_first = False
       for yes_words_row in yes_words_reader:
           if done_first:
               column_heading = yes_words_row[0]
               yes_words_dict[column_heading] = []
               yes_phrases = yes_words_row[1].split(",")
               for yes_phrase in yes_phrases:
                   clean_phrase = yes_phrase.rstrip().lstrip().lower()
                   if clean_phrase != "":
                       yes_words_dict[column_heading].append(clean_phrase)
           else:
               done_first = True
       return yes_words_dict

   '''
   Output handling
   '''

   def nextFileVariation(self,filename):
       i = filename.rfind(".")
       filename_l = filename[:i]
       filename_r = filename[i:]

       candidate_filename=""
       filename_counter = 1
       while (True):
           variation_filename = filename_l+"_"+str(filename_counter)
           candidate_filename = "spreadsheets/"+variation_filename+filename_r
           if (not (os.path.exists(candidate_filename))):
               break
           filename_counter += 1
       return variation_filename

   def makeOutputs(self):
       variation_filename = self.nextFileVariation(self.input_csv_filename)

       #spreadsheet for yes_words
       csv_filename = "spreadsheets/"+variation_filename+"_yes_phrases.csv"
       self.yes_words_csv = open(csv_filename, 'w')
       self.writeHeadings(self.yes_words_csv,self.yes_words_dict)

       #pdf for yes_words
       self.yes_words_pdf = "pdfs/"+variation_filename+"_yes_phrases.pdf"

       #spreadsheet for bayes
       csv_filename = "spreadsheets/"+variation_filename+"_bayes.csv"
       self.bayes_csv = open(csv_filename, 'w')
       self.writeHeadings(self.bayes_csv,self.classifiers)

       #pdf for bayes
       self.bayes_pdf = "pdfs/"+variation_filename+"_bayes.pdf"

   def closeOutputs(self,):
       self.yes_words_csv.close()
       self.bayes_csv.close()
      
   def writeHeadings(self,output,yes_words_dict):
       sorted_yes_words_dict = OrderedDict(sorted(yes_words_dict.items(), key=lambda t: t[0]))
       output.write("School name;")
       for key in sorted_yes_words_dict:
           output.write(key+";")
           output.write(key+" : URL;")
           output.write(key+" : Passage;")
       output.write("\n")

   '''
   Centeral extraction control

   '''

   def extract(self):
       self.makeOutputs()
       
       #load sfusd page with all school pages listed
       sfusd_schools_url = "http://www.sfusd.edu/en/schools/all-schools.html"
       soup, real_url, page_content = self.urlToSoup(sfusd_schools_url,"")

       links = soup.find("ul", {"class": "school-list"}).findAll("a")

       for link in links:
           content = link.contents[0]
           if (content != "More Info >"):
               self.extractOneRow([content,"http://www.sfusd.edu/en/"+link['href']])

       self.closeOutputs()

   def extractOneRow(self,input_row):
       school_name = input_row[0]
       school_sfusd_url = input_row[1]
       print "*****"
       print school_name

       soup, real_url, page_content = self.urlToSoup(school_sfusd_url,"")
       if not soup:
           return

       #initialize verdict
       curr_row_verdicts = self.makeVerdicts()

       #start accumulating links to explore from the school sites, starting with the main page
       links_to_explore = []
       identified_links = {}
       orig_url = ""
       orig_domain = ""

       div = soup.find("div", {"id": "content-inner"})
       if div:
           children = div.contents
           p = children[3]
           print p
           p_str = str(p)
           if (("Website: " in p_str) or ("School Loop: " in p_str)):
               a = p.findAll('a')
               if (len(a)>0):
                   new_url = a[0]['href']
                   links_to_explore.append(new_url)
                   identified_links[new_url] = True
           #only want to run classification on that inner content
           curr_row_verdicts = self.classify(soup,soup.find("div", {"id": "content"}),curr_row_verdicts,real_url,page_content,school_name)

       #now go through links_to_explore until run out, or until too many
       #for instance, lincolnhigh has this weird thing where it puts a return_url in the url
       #and thus keeps generating new links for way too long
       counter = 0
       while ((links_to_explore) and (counter < 100)):
           url = links_to_explore.pop()
           soup, real_url, page_content = self.urlToSoup(url,orig_url)
           if soup == None:
               continue

           if orig_url == "":
               orig_url = real_url
               orig_domain = tldextract.extract(real_url).domain

           #we're really doing this page.  increment counter
           counter += 1
           #classify with the current page
           curr_row_verdicts = self.classify(soup,soup,curr_row_verdicts,real_url,page_content,school_name)

           #get new urls to add to links_to_explore
           real_url_domain = tldextract.extract(real_url).domain
           #only want to get new links if we're on the main school page
           if (real_url_domain == orig_domain):
               new_links = self.getLinksFromSoup(soup,self.click_words)
               for new_link in new_links:
                   if not new_link in identified_links:
                       links_to_explore.append(new_link)
                       identified_links[new_link] = True

       #we've run out of links to explore, so we have our final answer
       self.writeVerdicts(school_name,curr_row_verdicts)

   def getLinksFromSoup(self,soup,click_words):
       new_links = []
       anchors = soup.findAll("a")
       for a in anchors:
           text = a.contents
           if ((len(text) > 0) and (text[0] != None) and (a.has_key('href'))):
               text = str(text[0]).lower()
               href = a['href'].lower()
               if ((not href.startswith("#"))\
                   and \
                   (not any(href.endswith(suffix) for suffix in ["pdf", "doc", "docx","jpg","jpeg","png","gif"]))\
                   and \
                   (any(click_word in text for click_word in click_words))):
                   new_links.append(href)
       return new_links

   def urlToSoup(self,url,base_url):
       try:
           #if url is global from the start, this should work
           page = urllib2.urlopen(url)
       except Exception:
           try:
               #url might just lack http stuff
               alt_url = "http://"+url
               page = urllib2.urlopen(alt_url)
           except Exception:
               try:
                  #url might be local, need a base url
                  alt_url = ""
                  if (base_url.endswith("/") and url.startswith("/")):
                      alt_url = base_url+url[1:]
                  elif (base_url.endswith("/") or url.startswith("/")):
                      alt_url = base_url+url
                  else:
                      alt_url = base_url+"/"+url
                  page = urllib2.urlopen(alt_url)
               except Exception:
                    print "Couldn't open url: "+url
                    return None, None, None


       real_url = page.geturl()
       page_content =  page.read()

       if page.info().get('Content-Encoding') == 'gzip':
           buf = StringIO(page_content)
           f = gzip.GzipFile(fileobj=buf)
           page_content = f.read()

       try:
           soup = BeautifulSoup(page_content)
       except:
           print "Couldn't soup url: "+url
           return None, None, None

       return soup, real_url, page_content

   '''
   Verdict handling
   '''

   def makeVerdicts(self):
       verdicts = {}
       verdicts["yes_words"] = self.blankVerdict(self.yes_words_dict)
       verdicts["bayes"] = self.blankVerdict(self.classifiers)
       return verdicts
   
   def blankVerdict(self,yes_words_dict):
       verdict = {}
       for entry in yes_words_dict:
           verdict[entry] = (False,[],[],0)
       return verdict

   def writeVerdicts(self,school_name,verdicts):
       self.writeVerdict(school_name, self.yes_words_csv, verdicts["yes_words"])
       self.writeVerdict(school_name, self.bayes_csv, verdicts["bayes"])

   def writeVerdict(self,school_name,output,verdict):
       sorted_verdict = OrderedDict(sorted(verdict.items(), key=lambda t: t[0]))
       output.write(str(school_name)+";")
       for key in sorted_verdict:
           value = sorted_verdict[key]
           output.write(str(value[0])+";")
           output.write(", ".join(value[1])+";")
           output.write(", ".join(value[2])+";")
       output.write("\n")

   '''
   PDF Stuff
   '''

   def makeSepPage(self, filename, url, key, school_name):
       c = canvas.Canvas(filename, pagesize=letter)
       width, height = letter
       c.setFillColor(orange) #choose your font colour
       c.drawString(30,3*height/4+40,school_name)
       c.drawString(30,3*height/4+20,key)
       link_width = c.stringWidth(url)
       link_rect = (30, 3*height/4, link_width, 10)
       c.setFillColorRGB(0,0,255) #choose your font colour
       c.drawString(30, 3*height/4, url)
       c.linkURL(url, link_rect)
       c.save()

   def savePDF(self, pdf_filename, parent_soup, target_node, yes_phrase, url, key, school_name):
       grandparent_node = target_node.parent.parent
       parent_node = target_node.parent
       parent_contents = parent_node.contents
       for i in range(len(parent_contents)):
           if parent_contents[i] == target_node:
               break
       content = str(target_node)
       text = content.lower()
       j = text.find(yes_phrase)
       tag = Tag(parent_soup, "div", [("style", "background-color:#FF8A0D")])
       if yes_phrase:
           tag.append(content[:j])
           bold = Tag(parent_soup, "b")
           bold.insert(0,content[j:(j + len(yes_phrase))])
           tag.append(bold)
           tag.append(content[(j + len(yes_phrase)):])
       else:
           tag.append(content)
       parent_node.contents[i] = tag

       body = Tag(parent_soup,"body")
       body.append(grandparent_node)
       weasyprint = HTML(string=body.prettify())
       tmp_filename = 'pdfs/tmp.pdf'
       weasyprint.write_pdf(tmp_filename,stylesheets=[CSS(string='body { font-size: 10px; font-family: serif !important }')])
       parent_node.contents[i] = target_node #return to old state

       sep_filename = "pdfs/sep.pdf"
       self.makeSepPage(sep_filename, url, key, school_name)

       merger = PdfFileMerger()
       if (os.path.exists(pdf_filename)):
           merger.append(PdfFileReader(file(pdf_filename, 'rb')))
       merger.append(PdfFileReader(file(sep_filename, 'rb')))
       merger.append(PdfFileReader(file(tmp_filename, 'rb')))
       merger.write(pdf_filename)

   '''
   Central classification functionality
   '''

   def classify(self, parent_soup, soup,curr_row_verdicts,url,page_content,school_name):
       curr_row_verdict = curr_row_verdicts["yes_words"]
       text = soup.findAll(text=True)
       visible_text = filter(self.visible,text)
       visible_text_string = self.soupToString(visible_text).lower()
       for key in self.yes_words_dict:
           #check if surpassed evidence limit for this key
           if curr_row_verdict[key][3] < 12:
               yes_phrases = self.yes_words_dict[key]
               for yes_phrase in yes_phrases:
                   if yes_phrase in visible_text_string:
                       matches = filter((lambda tag: self.hasYesPhrase(tag,yes_phrase)), visible_text)
                       for match in matches:
                           key_verdict = curr_row_verdict[key]
                           #check if surpassed evidence limit for this key
                           if key_verdict[3] < 12:
                               snippet = self.getSnippet(match,yes_phrase)
                               curr_row_verdict[key] = (True, key_verdict[1]+[url], key_verdict[2]+[snippet], key_verdict[3]+1)
                               self.savePDF(self.yes_words_pdf,parent_soup, match, yes_phrase, url, key, school_name)
       return curr_row_verdicts

   def visible(self, element):
       if element.parent.name in ['style', 'script', '[document]', 'head', 'title']:
           return False
       elif re.match('<!--.*-->', str(element)):
           return False
       return True

   def soupToString(self, elements):
       string = ""
       if type(elements) == list:
           for element in elements:
               string+=" "+self.soupToString(element)
           return string
       else:
           return str(elements).strip()

   def getSnippet(self,tag,yes_phrase):
       snippet = str(tag)

       #we don't want super long snippets
       if (len(snippet) > (1000+len(yes_phrase))):
           snippet_lower = snippet.lower()
           i = snippet_lower.find(yes_phrase)
           start_i = i - 300
           if start_i < 0:
               start_i = 0
           end_i = i + len(yes_phrase) + 300
           if end_i > (len(snippet)-1):
               end_i = len(snippet) - 1
           snippet = "..."+snippet[start_i:end_i]+"..."

       try:
           snippet_clean = unicodedata.normalize('NFKD', snippet).encode('ascii','ignore')
       except:
           snippet_clean = snippet

       snippet_full = "\""+snippet_clean+"\""
       return snippet_full

   def hasYesPhrase(self, tag, yes_phrase):
       text = str(tag)
       lower_text = text.lower()
       num_words = len(yes_phrase.split(" "))
       if yes_phrase in lower_text:
           if num_words > 1:
               return True
           #if this is a 1-word yes phrase, some extra processing
           left_fine = False
           right_fine = False
           l = lower_text.find(yes_phrase)
           if ((l == 0) or (not lower_text[l-1].isalpha())):
               left_fine = True
           r = l+len(yes_phrase)
           if ((r == len(lower_text)) or (not lower_text[r].isalpha())):
               right_fine = True
           if left_fine and right_fine:
               return True
       return False



       
def main():
    input_csv_filename = "schools.csv"
    yes_words_csv_filename = "yes_words.csv"
    click_strings = ["Academic Counseling","Counseling News","Who We Work With", \
                   "Advisory","Mission/Vision","Staff/Administration", \
                   "Wellness Center","Parent Information","Home","SARC", \
                   "Safe Schools","School Overview","About","Weekly Newsletter",\
                   "Alvarado_Notices_2013_09_03","SchoolPages",\
                   "Anti-Bullying Awareness","Anti-Bullying Policy","Overview",\
                   "Special Education Program/Inclusion","AVID","Counseling",\
                   "Special Education","Staff & Faculty Directory","About Lowell",\
                   "Lowell PTSA","About Attendance","Wellness 101","Freshmen",\
                   "Additional Information"]
    categorized_text_filename = "categorized_text_edited.txt"
    extractor = Extractor(input_csv_filename,yes_words_csv_filename,click_strings,categorized_text_filename)
    extractor.extract()
main()
