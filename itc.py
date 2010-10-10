#!/usr/bin/env python

import urllib2
import urllib
import cookielib
import re
import gzip
import StringIO

import mechanize

#import sys, logging
#logger = logging.getLogger("mechanize")
#logger.addHandler(logging.StreamHandler(sys.stdout))
#logger.setLevel(logging.INFO)

# There is an issue with Python 2.5 where it assumes the 'version'
# cookie value is always interger.  However, itunesconnect.apple.com
# returns this value as a string, i.e., "1" instead of 1.  Because
# of this we need a workaround that "fixes" the version field.
#
# More information at: http://bugs.python.org/issue3924
class MyCookieJar(cookielib.CookieJar):
    def _cookie_from_cookie_tuple(self, tup, request):
        name, value, standard, rest = tup
        version = standard.get('version', None)
        if version is not None:
            version = version.replace('"', '')
            standard["version"] = version
        return cookielib.CookieJar._cookie_from_cookie_tuple(self, tup, request)

class iTunesConnect(object):
    base_url = 'https://itunesconnect.apple.com'
    login_url = '/WebObjects/iTunesConnect.woa'
    report_url = 'https://reportingitc.apple.com/sales.faces'
    vendor_faces_url = 'https://reportingitc.apple.com/vendor_default.faces'


    def __init__(self, username, password):
        self.username = username
        self.password = password
        self._client = mechanize.Browser(factory=mechanize.DefaultFactory(i_want_broken_xhtml_support=True))
        self._client.set_handle_redirect(True)
        self._client.set_handle_referer(True)
        self._client.set_handle_robots(False)
        #self._client.set_debug_redirects(True)
        #self._client.set_debug_http(True)

    def _fetch_html(self, url, data=None):
        if data:
            data = urllib.urlencode(data)
        return self._opener.open(url, data).read()

    def login(self):
        page = self._client.open("%s%s" % (self.base_url, self.login_url))
        self._client.select_form(nr=0)
        self._client.form['theAccountName'] = self.username
        self._client.form['theAccountPW'] = self.password

        page = self._client.submit()
        body = page.read()
        if re.findall("session has expired", body):
            print "session expired"
            self.login()
            return

        page2 = self._client.follow_link(text="Sales and Trends")
        body = page2.read()
        page_param = re.findall("parameters':\{'(.*?)'", body)[0]
        ajax_id = re.findall("AJAX\.Submit\('(.*?)'", body)[0]
        self._client.select_form('defaultVendorPage')
        self._client.form.new_control("hidden", page_param, { 'value': page_param })
        self._client.form.new_control("hidden", 'AJAXREQUEST', { 'value': ajax_id })
        self._client.submit()

    def get_sales_report(self, date):
        page = self._client.open(self.report_url)
        body = page.read()

        #get all available daily report dates

        #check if passed in date is valid

        self._client.select_form('theForm')
        form = self._client.form
        form.set_all_readonly(False)
        form['theForm:xyz'] = 'notnormal'
        page_param = re.findall("parameters':\{'(.*?)'", body)[1]
        ajax_id = re.findall("AJAX\.Submit\('(.*?)'", body)[0]
        form.new_control("hidden", page_param, { 'value': page_param })
        form.new_control("hidden", 'AJAXREQUEST', { 'value': ajax_id })
        if date:
            form['theForm:datePickerSourceSelectElementSales'] = [date]
        form.find_control(type = "submit").disabled = True

        page = self._client.submit()
        body = page.read()

        self._client.open(self.report_url)
        self._client.select_form('theForm')
        form = self._client.form
        form.set_all_readonly(False)
        form['theForm:xyz'] = 'notnormal'
        form.new_control('hidden', 'theForm:downloadLabel2', { 'value': 'theForm:downloadLabel2'})
        form.find_control(type = "submit").disabled = True

        page = self._client.submit()
        filebuffer = page.read()
        iobuffer = StringIO.StringIO(filebuffer)
        gzip_io = gzip.GzipFile('rb', fileobj = iobuffer)
        filebuffer = gzip_io.read()
        gzip_io.close()
        #print filebuffer
        return Report(filebuffer, date)

    def parse_report(self, report_string):
        return Report(report_string)


class ReportEntry(object):
    def __str__(self):
        return self.__dict__

class ProductReport(object):
    def __init__(self, name, version):
        self.name = name
        self.version = version
        self.revenue = 0.0
        self.sale_count = 0
        self.upgrade_count = 0
        self.sales = []
        self.upgrades = []

    def add_entry(self, entry):
        if entry.Product_Type_Identifier in ['1', "1T"]:
            self.sale_count += int(entry.Units)
            self.revenue += float(entry.Customer_Price)
            self.sales.append(entry)
        elif entry.Product_Type_Identifier in ['7']:
            self.upgrade_count += int(entry.Units)
            self.upgrades.append(entry)

class Report(object):
    def __init__(self, data, date = ''):
        self.data = data
        self.date = date
        self.products = {}
        self._parse_report(data)

    def _get_product(self, report_entry):
        key = "%s_%s" % (report_entry.SKU, report_entry.Version)
        if key not in self.products:
            p = ProductReport(report_entry.Title, report_entry.Version)
            self.products[key] = p
        return self.products[key]

    def _parse_report(self, data):
        rows = data.split("\n")
        headers = rows[0].split("\t")
        for i, row in enumerate(rows[1:]):
            columns = row.split("\t") 
            if len(columns) == 1:
                continue
            e = ReportEntry()
            for i, column in enumerate(columns):
                setattr(e, headers[i].replace(" ", "_"), column)
            p = self._get_product(e)
            p.add_entry(e)

