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
from weasyprint import HTML


def nextFileVariation(filename):
    i = filename.rfind(".")
    filename_l = filename[:i]
    filename_r = filename[i:]

    candidate_filename=""
    counter = 1
    while (True):
        candidate_filename = filename_l+"_"+str(counter)+filename_r
        if (not (os.path.exists(candidate_filename))):
            break
        counter += 1
    return candidate_filename

def blankVerdict(yes_words_dict):
    verdict = {}
    for entry in yes_words_dict:
        verdict[entry] = (False,[],[])
    return verdict

def visible(element):
    if element.parent.name in ['style', 'script', '[document]', 'head', 'title']:
        return False
    elif re.match('<!--.*-->', str(element)):
        return False
    return True

def soupToString(elements):
    string = ""
    if type(elements) == list:
        for element in elements:
            string+=" "+soupToString(element)
        return string
    else:
        return elements.string.strip()

def getSnippet(visible_text_string,yes_phrase):
    i = visible_text_string.find(yes_phrase)
    start_i = i - 200
    if start_i < 0:
        start_i = 0
    end_i = i + len(yes_phrase) + 200
    if end_i > (len(visible_text_string)-1):
        end_i = len(visible_text_string) - 1
    snippet = visible_text_string[start_i:end_i]
    try:
        snippet_clean = unicodedata.normalize('NFKD', snippet).encode('ascii','ignore')
    except:
        snippet_clean = snippet
    snippet_full = "\"..."+snippet_clean+"...\""
    return snippet_full

def savePDFOld(page_content, yes_phrase, url, key, school_name):
    print yes_phrase
    lower_page = page_content.lower()
    i = lower_page.find(yes_phrase)
    new_page = page_content
    if (i > -1):
        #may not run, if the text is somehow broken up by tags or something, but highly unlikely
        new_page = page_content[:i]+"<b>"+page_content[i:(i + len(yes_phrase))]+"</b>"+page_content[(i + len(yes_phrase)):]

    weasyprint = HTML(string=new_page)
    weasyprint.write_pdf('test.pdf')
    exit()

def hasYesPhrase(tag, yes_phrase):
    contents = tag.contents
    if (len(contents) > 0):
        for content in contents:
            text = str(content)
            lower_text = text.lower()
            if yes_phrase in lower_text:
                return True
    return False

def savePDF(parent_soup, soup, yes_phrase, url, key, school_name):
    target_nodes = soup.findAll(lambda tag: hasYesPhrase(tag,yes_phrase))
    print target_nodes
    for target_node in target_nodes:
        contents = target_node.contents
        contents_len = len(contents)
        for i in range(contents_len):
            content = str(contents[i])
            text = str(content).lower()
            if yes_phrase in text:
                tag = Tag(parent_soup, "div", [("style", "background-color:green")])
                tag.insert(0,content)
                target_node.contents[i] = tag
                
        weasyprint = HTML(string=target_node.prettify())
        weasyprint.write_pdf('test.pdf')
        print target_node
    #print soup.prettify()
    exit()

def classify(parent_soup, soup,yes_words_dict,curr_row_verdict,url,page_content,school_name):
    text = soup.findAll(text=True)
    visible_text = filter(visible,text)
    visible_text_string = soupToString(visible_text).lower()
    for key in yes_words_dict:
        yes_phrases = yes_words_dict[key]
        for yes_phrase in yes_phrases:
            if yes_phrase in visible_text_string:
                #print "yes_phrase: "+yes_phrase
                #print visible_text_string
                #print yes_phrase in visible_text_string
                snippet = getSnippet(visible_text_string,yes_phrase)
                key_verdict = curr_row_verdict[key]
                curr_row_verdict[key] = (True, key_verdict[1]+[url], key_verdict[2]+[snippet])
                #savePDFOld(page_content, yes_phrase, url, key, school_name)
                savePDF(parent_soup,soup, yes_phrase, url, key, school_name)
                break
    return curr_row_verdict

def getLinksFromSoup(soup,click_words):
    new_links = []
    anchors = soup.findAll("a")
    for a in anchors:
        text = a.contents
        if ((len(text) > 0) and (text[0] != None) and (a.has_key('href'))):
            text = str(text[0]).lower()
            href = a['href'].lower()
            #print href
            #print href.startswith("#")
            #print (not any(href.endswith(suffix) for suffix in ["pdf", "doc", "docx"]))
            #print text
            #print any(click_word in text for click_word in click_words)
            if ((not href.startswith("#"))\
                and \
                (not any(href.endswith(suffix) for suffix in ["pdf", "doc", "docx","jpg","jpeg","png","gif"]))\
                and \
                (any(click_word in text for click_word in click_words))):
                new_links.append(href)
    return new_links

def runExtractionOneRow(input_row,output,yes_words_dict,click_words):
    school_name = input_row[0]
    school_sfusd_url = input_row[1]
    print "*****"
    print school_name

    soup, real_url, page_content = urlToSoup(school_sfusd_url,"")
    if not soup:
        return

    #initialize verdict
    curr_row_verdict = blankVerdict(yes_words_dict)
    
    #start accumulating links to explore from the school sites, starting with the main page
    links_to_explore = []
    identified_links = {}
    orig_url = ""
    orig_domain = ""
    
    div = soup.find("div", {"id": "content-inner"})
    if div:
        #only want to run classification on that inner content
        curr_row_verdict = classify(soup,soup.find("div", {"id": "content"}),yes_words_dict,curr_row_verdict,real_url,page_content, school_name)
        children = div.findChildren()
        p = children[3]
        print p
        if ("Website: " in str(p)):
            a = p.findAll('a')
            if (len(a)>0):
                new_url = a[0]['href']
                links_to_explore.append(new_url)
                identified_links[new_url] = True

    #now go through links_to_explore until run out, or until too many
    #for instance, lincolnhigh has this weird thing where it puts a return_url in the url
    #and thus keeps generating new links for way too long
    counter = 0
    while ((links_to_explore) and (counter < 100)):
        url = links_to_explore.pop()
        soup, real_url, page_content = urlToSoup(url,orig_url)
        if soup == None:
            continue
        
        if orig_url == "":
            orig_url = real_url
            orig_domain = tldextract.extract(real_url).domain

        #we're really doing this page.  increment counter
        counter += 1
        #classify with the current page
        curr_row_verdict = classify(soup,soup,yes_words_dict,curr_row_verdict,real_url,page_content,school_name)

        #get new urls to add to links_to_explore
        real_url_domain = tldextract.extract(real_url).domain
        #only want to get new links if we're on the main school page
        if (real_url_domain == orig_domain):
            new_links = getLinksFromSoup(soup,click_words)
            for new_link in new_links:
                if not new_link in identified_links:
                    links_to_explore.append(new_link)
                    identified_links[new_link] = True

    #we've run out of links to explore, so we have our final answer
    writeVerdict(school_name,output,curr_row_verdict)
    
def writeVerdict(school_name,output,verdict):
    sorted_verdict = OrderedDict(sorted(verdict.items(), key=lambda t: t[0]))
    output.write(str(school_name)+";")
    for key in sorted_verdict:
        value = sorted_verdict[key]
        output.write(str(value[0])+";")
        output.write(", ".join(value[1])+";")
        output.write(", ".join(value[2])+";")
    output.write("\n")

def processClickStrings(click_strings):
    click_words = []
    for string in click_strings:
        new_words =  re.split('[\W^_]+',string)
        for word in new_words:
            word_lower = word.lower()
            if (not word_lower in click_words):
                click_words.append(word_lower)
    return click_words

def processYesWords(yes_words_csv): 
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

def writeHeadings(output,yes_words_dict):
    sorted_yes_words_dict = OrderedDict(sorted(yes_words_dict.items(), key=lambda t: t[0]))
    output.write("School name;")
    for key in sorted_yes_words_dict:
        output.write(key+";")
        output.write(key+" : URL;")
        output.write(key+" : Passage;")
    output.write("\n")

def urlToSoup(url,base_url):
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
        print "gzipped"
        buf = StringIO(page_content)
        f = gzip.GzipFile(fileobj=buf)
        page_content = f.read()

    try:
        soup = BeautifulSoup(page_content)
    except:
        print "Couldn't soup url: "+url
        return None, None, None

    return soup, real_url, page_content

def runExtraction(input_csv,yes_words_csv):
    #process input
    csvfile = open(input_csv, 'rb')
    input_reader = csv.reader(csvfile, delimiter=',')

    #process yes_words
    yes_words_dict = processYesWords(yes_words_csv)

    #process click_strings
    click_strings = ["Academic Counseling","Counseling News","Who We Work With", \
                   "Advisory","Mission/Vision","Staff/Administration", \
                   "Wellness Center","Parent Information","Home","SARC", \
                   "Safe Schools","School Overview","About","Weekly Newsletter",\
                   "Alvarado_Notices_2013_09_03","SchoolPages",\
                   "Anti-Bullying Awareness","Anti-Bullying Policy","Overview",\
                   "Special Education Program/Inclusion","AVID","Counseling",\
                   "Special Education","Staff & Faculty Directory","About Lowell",\
                   "Lowell PTSA","About Attendance","Wellness 101","Freshmen"]
    click_words = processClickStrings(click_strings)

    #make output
    output_filename = nextFileVariation(input_csv)
    output = open(output_filename, 'w')
    writeHeadings(output,yes_words_dict)

    
    #load sfusd page with all school pages listed
    
    sfusd_schools_url = "http://www.sfusd.edu/en/schools/all-schools.html"
    soup, real_url, page_content = urlToSoup(sfusd_schools_url,"")
        
    links = soup.find("ul", {"class": "school-list"}).findAll("a")

    for link in links:
        content = link.contents[0]
        if (content != "More Info >"):
            runExtractionOneRow([content,"http://www.sfusd.edu/en/"+link['href']],output,yes_words_dict,click_words)

    output.close()
        
def main():
    input_csv = "schools.csv"
    yes_words_csv = "yes_words.csv"
    runExtraction(input_csv,yes_words_csv)
main()
