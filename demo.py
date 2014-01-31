from BeautifulSoup import BeautifulSoup
import urllib
import urllib2
import csv
import os
import re
import json
from collections import OrderedDict

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
        verdict[entry] = (False,"","")
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

def classify(soup,yes_words_dict,curr_row_verdict,url):
    text = soup.findAll(text=True)
    visible_text = filter(visible,text)
    visible_text_string = soupToString(visible_text)
    for key in yes_words_dict:
        if curr_row_verdict[key][0]:
            #we've already found evidence of this program. don't bother to look
            continue
        yes_phrases = yes_words_dict[key]
        if any(yes_phrase in visible_text_string for yes_phrase in yes_phrases):
            curr_row_verdict[key] = (True, url,"")
    return curr_row_verdict

def getLinksFromSoup(soup,click_words):
    new_links = []
    anchors = soup.findAll("a")
    for a in anchors:
        text = a['text']
        if (click_word in text for click_word in click_words):
            new_links.append(a['href'])
    return new_links

def runExtractionOneRow(input_row,output,yes_words_dict,click_words):
    #get first google result for school name and "sfsud"
    school_name = input_row[0]
    google_url = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&'
    url = google_url + urllib.urlencode({'q' : (school_name+" sfsud").encode('utf-8')})
    raw_res = urllib.urlopen(url).read()
    results = json.loads(raw_res)
    hit1 = results['responseData']['results'][0]
    sfsud_url = urllib.unquote(hit1['url'])
    print "*****"
    print sfsud_url
    
    #load page for first google result
    page = urllib2.urlopen(sfsud_url)
    real_sfsud_url = page.geturl()

    #classification on first google result
    soup = BeautifulSoup(page.read())
    curr_row_verdict = blankVerdict(yes_words_dict)
    curr_row_verdict = classify(soup,yes_words_dict,curr_row_verdict,real_sfsud_url)

    #start accumulating links to explore from the school sites, starting with the main page
    links_to_explore = []
    div = soup.find("div", {"id": "content-inner"})
    if div:
        print "div exists"
        children = div.findChildren()
        p = children[3]
        print str(p)
        if ("Website: " in str(p)):
            print "website in string version"
            a = p.findAll('a')
            if (len(a)>0):
                print "anchors present"
                links_to_explore.append(a[0]['href'])

    #now go through links_to_explore until run out
    while links_to_explore:
        url = links_to_explore.pop()
        print url
        page = urllib2.urlopen(url)
        real_url = page.geturl()
        soup = BeautifulSoup(page.read())
        #classify with the current page
        curr_row_verdict = classify(soup,yes_words_dict,curr_row_verdict,real_url)
        #get new urls to add to links_to_explore
        new_links = getLinksFromSoup(soup,click_words)
        links_to_explore += new_links

    #we've run out of links to explore, so we have our final answer
    writeVerdict(output,curr_row_verdict)
    
def writeVerdict(output,verdict):
    sorted_verdict = OrderedDict(sorted(verdict.items(), key=lambda t: t[0]))
    for key in sorted_verdict:
        value = sorted_verdict[key]
        output.write(str(value[0])+",")
        output.write(value[1]+",")
        output.write(value[2]+",")
    output.write("\n")

def processClickStrings(click_strings):
    click_words = []
    for string in click_strings:
        new_words =  re.split('[\W^_]+',string)
        for word in new_words:
            if (not word in click_words):
                click_words.append(word)
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
                yes_words_dict[column_heading].append(yes_phrase.rstrip().lstrip())
        else:
            done_first = True
    return yes_words_dict

def writeHeadings(output,yes_words_dict):
    sorted_yes_words_dict = OrderedDict(sorted(yes_words_dict.items(), key=lambda t: t[0]))
    for key in sorted_yes_words_dict:
        output.write(key+",")
        output.write(key+" : URL,")
        output.write(key+" : Passage,")
    output.write("\n")

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

    done_first = False
    for input_row in input_reader:
        if (done_first):
            runExtractionOneRow(input_row, output, yes_words_dict, click_words)
        else:
            done_first = True

    output.close()
        
def main():
    input_csv = "schools.csv"
    yes_words_csv = "yes_words.csv"
    runExtraction(input_csv,yes_words_csv)
main()
