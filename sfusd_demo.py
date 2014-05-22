import os
import sys
from BeautifulSoup import BeautifulSoup, Tag, NavigableString
import urllib
import urllib2
import csv
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
from reportlab.lib.colors import orange, black
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from text.classifiers import NaiveBayesClassifier
import logging
from nltk import word_tokenize, wordpunct_tokenize
from nltk.stem.lancaster import LancasterStemmer
import operator
from RAKE.rake import *

class Extractor:
   input_csv_filename = ""
   use_bayes = False
    
   classifiers = {}
   yes_words_dict = {}
   click_words = []
   maybe_words = {}

   yes_words_csv = None # a file object for the csv
   yes_words_pdf = "" # the filename for the pdf
   bayes_csv = None # a file object for the csv
   bayes_pdf = "" # the filename for the pdf

   debug = False

   def __init__(self, input_csv_filename, yes_words_csv_filename, click_strings, categorized_text_filename, use_bayes):
       #process input
       #csvfile = open(input_csv, 'rb')
       #input_reader = csv.reader(csvfile, delimiter=',')
       self.input_csv_filename = input_csv_filename
       self.use_bayes = use_bayes

       #process yes_words
       self.yes_words_dict = self.processYesWords(yes_words_csv_filename)

       #process click_strings
       self.click_words = self.processClickStrings(click_strings)

       if (self.use_bayes):
          #process categorized data
          self.classifiers = self.processTextData(categorized_text_filename)

       #process maybe words
       self.processTextDataForMaybeWords(categorized_text_filename)
       
       #get rid of annoying weasyprint logging
       logger = logging.getLogger('weasyprint')
       logger.handlers = []  # Remove the default stderr handler
       logger.addHandler(logging.FileHandler('logs/weasyprint.log'))

   '''
   Input processing
   '''

   def processTextDataForMaybeWords(self, filename):
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
           classify_str_clean = unicode(classify_str, errors='ignore')
           for i in range(len(columns)):
               column = columns[i]
               if column == "*":
                   training_data[column_names[i]].append(classify_str_clean)

       maybe_words = {}
       for key in training_data:
           print key
           #self.maybe_words[key] = self.getMaybeWords(training_data[key])
           self.maybe_words[key] = self.getMaybeWordsRake(training_data[key])
       return

   def getMaybeWordsRake(self, text_ls):
      text = (".  ").join(text_ls)

      # Split text into sentences
      sentenceList = splitSentences(text)
      #stoppath = "RAKE/FoxStoplist.txt" #Fox stoplist contains "numbers", so it will not find "natural numbers" like in Table 1.1
      stoppath = "RAKE/SmartStoplist.txt" #SMART stoplist misses some of the lower-scoring keywords in Figure 1.5, which means that the top 1/3 cuts off one of the 4.0 score words in Table 1.1
      stopwordpattern = buildStopwordRegExPattern(stoppath)

      # generate candidate keywords
      phraseList = generateCandidateKeywords(sentenceList, stopwordpattern)

      # calculate individual word scores
      wordscores = calculateWordScores(phraseList)

      # generate candidate keyword scores
      keywordcandidates = generateCandidateKeywordScores(phraseList, wordscores)
      if debug: print keywordcandidates

      sortedKeywords = sorted(keywordcandidates.iteritems(), key=operator.itemgetter(1), reverse=True)
      if debug: print sortedKeywords

      totalKeywords = len(sortedKeywords)
      if debug: print totalKeywords
      print sortedKeywords[0:(totalKeywords/3)]

   def getMaybeWords(self, text_ls):
      ignoreWords = ["","have","her","there","the","be","to","of","and","a","in","that","it","for","on","with","as","at","this","but","his","by","from","they","or","an","will","would","so","even","is","be","am","are"];

      word_ls = []
      for text in text_ls:
         word_ls += wordpunct_tokenize(text)
         
      frequencies = {}
      st = LancasterStemmer()
      for word in word_ls:
         if not word[0].isalpha():
            continue
         if word in ignoreWords:
            continue
         word_stem = st.stem(word)
         if word_stem in frequencies:
            frequencies[word_stem] += 1
         else:
            frequencies[word_stem] = 1

      sorted_frequencies = sorted(frequencies.iteritems(), key = operator.itemgetter(1), reverse =  True)
      #print sorted_frequencies

      max_words = 30
      if len(sorted_frequencies) < max_words:
         max_words = len(sorted_frequencies)
      word_tuples = sorted_frequencies[0:max_words]
      words = [tuple[0] for tuple in word_tuples]
      print words
      return words

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
           classify_str_clean = unicode(classify_str, errors='ignore')
           for i in range(len(columns)):
               column = columns[i]
               if column == "*":
                   training_data[column_names[i]].append((classify_str_clean,'pos'))
               else:
                   training_data[column_names[i]].append((classify_str_clean,'neg'))

       self.classifiers = {}
       for key in training_data:
           self.classifiers[key] = NaiveBayesClassifier(training_data[key])
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
       yes_words_reader = csv.reader(csvfile, delimiter=';')
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
           candidate_filename = "spreadsheets/"+variation_filename+"_yes_phrases.csv"
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
       output.write("School name,")
       for key in sorted_yes_words_dict:
           output.write(key+",")
           output.write(key+" : URL,")
           output.write(key+" : Passage,")
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

       if self.debug:
          cont = raw_input("Continue? ")
          if cont[0] == "n" or cont[0] == "N":
             exit()

       soup, real_url, page_content = self.urlToSoup(school_sfusd_url,"")
       if not soup:
           return

       #initialize verdict
       curr_row_verdicts = self.makeVerdicts()

       #start accumulating links to explore from the school sites, starting with the main page
       links_to_explore = []
       identified_links = {}
       visited_links = {}
       visited_links[real_url] = True
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
           curr_row_verdicts = self.classify(soup,soup.find("div", {"id": "content"}),curr_row_verdicts,real_url,school_name)

       #now go through links_to_explore until run out, or until too many
       #for instance, lincolnhigh has this weird thing where it puts a return_url in the url
       #and thus keeps generating new links for way too long
       counter = 0
       while ((links_to_explore) and (counter < 50)):
           url = links_to_explore.pop(0)
           soup, real_url, page_content = self.urlToSoup(url,orig_url)
           if real_url in visited_links:
              continue
           visited_links[real_url] = True
           print real_url
           if soup == None:
               continue

           if orig_url == "":
               orig_url = real_url
               orig_domain = tldextract.extract(real_url).domain

           #we're really doing this page.  increment counter
           counter += 1
           #classify with the current page
           curr_row_verdicts = self.classify(soup,soup,curr_row_verdicts,real_url,school_name)

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
       self.writeVerdictsPDF(school_name,curr_row_verdicts)

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
       try:
           page_content =  page.read()
       except Exception:
           print "Couldn't open url: "+url
           return None, None, None

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
           verdict[entry] = (0,[],[],0)
       return verdict

   def writeVerdicts(self,school_name,verdicts):
       self.writeVerdict(school_name, self.yes_words_csv, verdicts["yes_words"])
       self.writeVerdict(school_name, self.bayes_csv, verdicts["bayes"])

   def writeVerdict(self,school_name,output,verdict):
       sorted_verdict = OrderedDict(sorted(verdict.items(), key=lambda t: t[0]))
       output.write("\""+str(school_name)+"\",")
       for key in sorted_verdict:
           value = sorted_verdict[key]
           output.write(str(value[0])+",")
           urls = map(lambda x: "\""+x+"\"",value[1])
           snippets = map(lambda x: "\""+x+"\"",value[2])
           output.write("; ".join(urls)+",")
           output.write("; ".join(snippets)+",")
       output.write("\n")

   '''
   PDF Stuff
   '''
   
   def writeVerdictsPDF(self,school_name,verdicts):
       page_filename = "pdfs/page.pdf"
       self.writeVerdictPDF(school_name, page_filename, verdicts["yes_words"])

       pdf_filename = self.yes_words_pdf
       merger = PdfFileMerger()
       if (os.path.exists(pdf_filename)):
           merger.append(PdfFileReader(file(pdf_filename, 'rb')))
       merger.append(PdfFileReader(file(page_filename, 'rb')))
       merger.write(pdf_filename)

   def writeVerdictPDF(self,school_name, filename, verdict):
       sorted_verdict = OrderedDict(sorted(verdict.items(), key=lambda t: t[0]))
       
       styles = getSampleStyleSheet()
       styleN = styles["BodyText"]
       styleN.alignment = TA_LEFT
       styleBH = styles["Normal"]
       styleBH.alignment = TA_CENTER
       
       for (k,v) in sorted_verdict.iteritems():
              print "\n ------------- \n".join(set(map(lambda (x): x.strip(), v[2])))
       
       data= [map(lambda (k,v): Paragraph(k, styleBH), sorted_verdict.iteritems()),
              map(lambda (k,v): Paragraph("<br/> ------------- <br/>".join(set(map(lambda (x): x.strip(), v[2]))), styleN), sorted_verdict.iteritems())]

       cwidth = 120
       table = Table(data, colWidths=[cwidth]*len(sorted_verdict))

       table.setStyle(TableStyle([
          ('INNERGRID', (0,0), (-1,-1), 0.25, black),
          ('BOX', (0,0), (-1,-1), 0.25, black),
          ('VALIGN',(0,0),(-1,-1),'TOP')
          ]))
          
       margin = 20
       w, h = table.wrap(0,0)
       pagewidth = w+margin*2
       pageheight = h+margin*3
       c = canvas.Canvas(filename, pagesize=(pagewidth,pageheight))
       
       table.drawOn(c, margin, pageheight - h - 2*margin)

       c.setFillColor(black) #choose your font colour
       c.drawString(margin,pageheight-margin,school_name)
       
       c.save()

   def makeSepPage(self, filename, url, key, school_name):
       c = canvas.Canvas(filename, pagesize=letter)
       width, height = letter
       c.setFillColor(black) #choose your font colour
       c.drawString(30,3*height/4+40,school_name)
       c.setFillColor(orange) #choose your font colour
       c.drawString(30,3*height/4+20,key)
       link_width = c.stringWidth(url)
       link_rect = (30, 3*height/4, link_width, 10)
       c.setFillColorRGB(0,0,255) #choose your font colour
       c.drawString(30, 3*height/4, url)
       c.linkURL(url, link_rect)
       c.save()

   def makeSepPageURL(self, filename, url, keys, school_name):
       c = canvas.Canvas(filename, pagesize=letter)
       width, height = letter
       x = 30
       y = height - 60
       c.setFillColor(black) #choose your font colour
       c.drawString(x,y,school_name)
       c.setFillColor(orange) #choose your font colour
       for key in keys:
          y -= 20
          c.drawString(x,y,key)
       y -= 20
       link_width = c.stringWidth(url)
       link_rect = (x, y, link_width, 10)
       c.setFillColorRGB(0,0,255) #choose your font colour
       c.drawString(x, y, url)
       c.linkURL(url, link_rect)
       c.save()

   def highlightedNode(self, target_node, yes_phrase, parent_soup):
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
       return tag

   def highlightNode(self,target_node, yes_phrase, parent_soup):
       new_node = self.highlightedNode(target_node, yes_phrase, parent_soup)
       self.replaceNode(target_node, new_node)

   def replaceNode(self, old_node, new_node):
       parent_node = old_node.parent
       parent_contents = parent_node.contents
       for i in range(len(parent_contents)):
          if parent_contents[i] == old_node:
             break
       parent_node.contents[i] = new_node

   def savePDFURL(self, pdf_filename, soup, url, keys, school_name):
       try:
          weasyprint = HTML(string=soup.prettify())
          tmp_filename = 'pdfs/tmp.pdf'
          weasyprint.write_pdf(tmp_filename,stylesheets=[CSS(string='body { font-size: 10px; font-family: serif !important }')])
       except:
          print "weasyprint failed on url: "+url
          return

       sep_filename = "pdfs/sep.pdf"
       self.makeSepPageURL(sep_filename, url, keys, school_name)

       merger = PdfFileMerger()
       if (os.path.exists(pdf_filename)):
           merger.append(PdfFileReader(file(pdf_filename, 'rb')))
       merger.append(PdfFileReader(file(sep_filename, 'rb')))
       merger.append(PdfFileReader(file(tmp_filename, 'rb')))
       merger.write(pdf_filename)

   def savePDF(self, pdf_filename, parent_soup, target_node, yes_phrase, url, key, school_name):
       if target_node:
          grandparent_node = target_node.parent.parent
          tag = self.highlightedNode(target_node, yes_phrase, parent_soup)
          self.replaceNode(target_node, tag)
          body = Tag(parent_soup,"body")
          body.append(grandparent_node)
       else:
          body = parent_soup
       try:
          weasyprint = HTML(string=body.prettify())
          tmp_filename = 'pdfs/tmp.pdf'
          weasyprint.write_pdf(tmp_filename,stylesheets=[CSS(string='body { font-size: 10px; font-family: serif !important }')])
       except:
          print "weasyprint failed on url: "+url
          if target_node:
             self.replaceNode(tag, target_node) #return to old state
          return

       if target_node:
          self.replaceNode(tag, target_node) #return to old state

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

   def classify(self, parent_soup, soup,curr_row_verdicts, url, school_name):
       curr_row_verdict = curr_row_verdicts["yes_words"]
       text = soup.findAll(text=True)
       visible_text = filter(self.visible,text)

       #bayes stuff
       if (self.use_bayes):
           visible_text_str = self.soupToString(visible_text)
           self.classifyBayesShort(visible_text_str, curr_row_verdicts, url, parent_soup, school_name)

       #yes words stuff
       keys = []
       for tag in visible_text:
           text = self.nodeContent(tag)
           one_tag_keys = self.classifyYesWords(text, curr_row_verdicts, tag, url, parent_soup, school_name)

       #verdict from all analyses, in their separate dicts
       return curr_row_verdicts

   def classifyYesWords(self, text, curr_row_verdicts, tag, url, parent_soup, school_name):
       curr_row_verdict = curr_row_verdicts["yes_words"]
       lower_text = text.lower()
       found_keys = []
       for key in self.yes_words_dict:
           yes_phrase = self.yes_words_dict[key]
           for yes_phrase in yes_phrase:
               if self.textHasYesPhrase(lower_text, yes_phrase):
                   key_verdict = curr_row_verdict[key]
                   #check if surpassed evidence limit for this key
                   if key_verdict[3] < 12:
                       snippet = self.getSnippet(text,yes_phrase,tag)
                       key_verdict_urls = key_verdict[1]
                       key_verdict_snippets = key_verdict[2]
                       if not url in key_verdict_urls:
                          key_verdict_urls.append(url)
                       if (snippet in key_verdict_snippets):
                          #often we'll get a link that appears on many pages, like "Alamo PTA"
                          #add the url and snippet, but don't up the counter
                          curr_row_verdict[key] = (1, key_verdict_urls, key_verdict_snippets+[snippet], key_verdict[3])
                          #highlight the node in case we print this page
                          self.highlightNode(tag, yes_phrase, parent_soup)
                          #but don't add this key to the found_keys.  if no new evidence found in other iterations, won't print page
                          #found_keys.append(key)
                       else:
                          #new evidence
                          #add the url and snippet, up the counter
                          curr_row_verdict[key] = (1, key_verdict_urls, key_verdict_snippets+[snippet], key_verdict[3]+1)
                          #highlight the node, since we'll be printing this page
                          self.highlightNode(tag, yes_phrase, parent_soup)
                          #add key to the found_keys so we print this page
                          found_keys.append(key)
                          
       return found_keys

   def classifyBayes(self, text, curr_row_verdicts, tag, url, parent_soup, school_name):
       curr_row_verdict = curr_row_verdicts["bayes"]
       text_clean = unicode(text, errors='ignore')
       for key in self.classifiers:
           key_verdict = curr_row_verdict[key]
           #check if surpassed evidence limit for this key 
           if key_verdict[3] < 12:
               classifier = self.classifiers[key]
               ans = classifier.classify(text_clean)
               if ans == "pos":
                   snippet = self.getSnippet(text, None, tag)
                   key_verdict_urls = key_verdict[1]
                   if not url in key_verdict_urls:
                       key_verdict_urls.append(url)
                   curr_row_verdict[key] = (1, key_verdict_urls, key_verdict[2]+[snippet], key_verdict[3]+1)
                   self.savePDF(self.bayes_pdf, parent_soup, tag, None, url, key, school_name)

   def classifyBayesShort(self, text, curr_row_verdicts, url, parent_soup, school_name):
       curr_row_verdict = curr_row_verdicts["bayes"]
       text_clean = unicode(text, errors='ignore')
       for key in self.classifiers:
           key_verdict = curr_row_verdict[key]
           #check if surpassed evidence limit for this key 
           if key_verdict[3] < 12:
               classifier = self.classifiers[key]
               ans = classifier.classify(text_clean)
               if ans == "pos":
                   print key
                   snippet = text
                   key_verdict_urls = key_verdict[1]
                   if not url in key_verdict_urls:
                       key_verdict_urls.append(url)
                   curr_row_verdict[key] = (1, key_verdict_urls, key_verdict[2]+[snippet], key_verdict[3]+1)
                   self.savePDF(self.bayes_pdf, parent_soup, None, None, url, key, school_name)
                   

   def isHeader(self, tag):
       tag_length = len(self.nodeContent(tag).split(" "))
       if (tag_length > 10):
              return False
       next_tag = self.nextSibling(tag)
       if next_tag == None:
              return False
       next_tag_length = len(self.nodeContent(next_tag).split())
       if (next_tag_length > 10):
              return True
       return False
       
   #the next sibling with text in it    
   def nextSibling(self, tag):
       if isinstance(tag, NavigableString):
              ntag = tag.parent.nextSibling
       else:
              ntag = tag.nextSibling
       #want text in it
       if (ntag == None):
              return None
       if (len(self.nodeContent(ntag)) == 0 or (not self.visible(ntag))):
              ntag = self.nextSibling(ntag)
       return ntag

   def getSnippet(self,snippet,yes_phrase,tag):
       if self.isHeader(tag):
           next_sibling = self.nextSibling(tag)
           next_sibling_text = self.nodeContent(next_sibling)
           print "NEXT SIBLING TEXT:"
           print next_sibling_text
           print isinstance(next_sibling, NavigableString)
           print isinstance(next_sibling, Tag)
           snippet = snippet + "\n" + next_sibling_text
          
       #we don't want super long snippets
       if (not yes_phrase):
           if len(snippet) > 1200:
               snippet = snippet[:1200]
       elif (len(snippet) > (1000+len(yes_phrase))):
           snippet_lower = snippet.lower()
           i = snippet_lower.find(yes_phrase)
           start_i = i - 300
           if start_i < 0:
               start_i = 0
           end_i = i + len(yes_phrase) + 300
           if end_i > (len(snippet)-1):
               end_i = len(snippet) - 1
           snippet = "..."+snippet[start_i:end_i]+"..."
              
       #snippet_clean = unicodedata.normalize('NFKD', unicode(snippet)).encode('utf8','ignore')
       snippet_clean = snippet.decode("utf8","ignore").encode("utf8","ignore")

       snippet_clean = snippet_clean.replace('\n', ' ')
       snippet_clean = snippet_clean.replace('\r', ' ')
       #print snippet_clean
       #print ord(snippet_clean[0])

       #snippet_full = "\""+snippet_clean+"\""
       return snippet_clean
                   

   def textHasYesPhrase(self, lower_text, yes_phrase):
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

   def visible(self, element):
       reject_tags = ['style', 'script', '[document]', 'head', 'title']
       if (element.parent.name in reject_tags) or (isinstance(element, Tag) and element.name in reject_tags):
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
           
   def nodeContent(self, tag):
       if isinstance(tag, Tag):
              return tag.getText()
       elif isinstance(tag, NavigableString):
              return str(tag)
       else:
              return ""







       
def main():
    input_csv_filename = "schools.csv"
    yes_words_csv_filename = "yes_words_updated.csv"
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
    extractor = Extractor(input_csv_filename,yes_words_csv_filename,click_strings,categorized_text_filename, False)
    extractor.extract()
main()
