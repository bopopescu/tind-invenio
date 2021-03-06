# coding=utf-8

# This file is part of Invenio.
# Copyright (C) 2011, 2012 CERN.
#
# Invenio is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

# pylint: disable=C0103
"""Invenio Interface for bibz39 live view."""
import cgi

from PyZ3950 import zoom, zmarc
from invenio.bibrecord import create_record, record_add_field, record_xml_output, \
    record_delete_field


try:
    import json
except ImportError:
    import simplejson as json

from invenio.errorlib import register_exception

try:
    from invenio.config import CFG_Z39_SERVER
except ImportError:
    from invenio.bibz39_config import CFG_Z39_SERVER
from invenio.config import CFG_SITE_URL, CFG_SITE_SECURE_URL
from invenio.access_control_engine import acc_authorize_action
from invenio.webinterface_handler import WebInterfaceDirectory, wash_urlargd
from invenio.webpage import page
from invenio.webuser import page_not_authorized
from invenio.urlutils import redirect_to_url
from invenio.bibedit_utils import create_cache
from invenio.bibedit_dblayer import reserve_record_id
from invenio.webuser import getUid


class WebInterfacebibz39Pages(WebInterfaceDirectory):
    """Defines the set of /bibz39 pages."""

    _exports = ['']
    _request_type_dict = {"ISBN": "isbn", "Title": "ti", "Authors": "au"}

    def index(self, req, form):
        """ Display live bibz39 queue
        """
        referer = '/admin2/bibz39/'
        navtrail = ' <a class="navtrail" href=\"%s/help/admin\">Admin Area</a> ' % CFG_SITE_URL

        auth_code, auth_message = acc_authorize_action(req, 'runbibedit')
        if auth_code != 0:
            return page_not_authorized(req=req, referer=referer,
                                       text=auth_message, navtrail=navtrail)

        argd = wash_urlargd(form, {
            'search': (str, ''),
            'marcxml': (str, ''),
            'server': (list, []),
            'search_type': (str, ''),
        })

        if argd['marcxml']:
            uid = getUid(req)
            new_recid = reserve_record_id()
            record = create_record(argd["marcxml"])[0]
            record_delete_field(record, '001')
            record_delete_field(record, '005')
            record_add_field(record, '001',
                             controlfield_value=str(new_recid))
            create_cache(new_recid, uid, record, True)
            redirect_to_url(req, '{0}/record/edit/#state=edit&recid={1}'.format(CFG_SITE_SECURE_URL,
                                                                                new_recid))

        body_content = ''

        body_content += self.generate_request_form(argd)

        if "search" in argd and argd["search"] and 'search_type' in argd and argd["search_type"] in \
                self._request_type_dict:

            conn = None
            list_of_record = []
            errors = {}

            res = []
            err = False
            for server in argd["server"]:
                try:
                    errors[server] = {"internal": [], "remote": []}
                    conn = zoom.Connection(CFG_Z39_SERVER[server]["address"],
                                           CFG_Z39_SERVER[server]["port"],
                                           user=CFG_Z39_SERVER[server].get("user", None),
                                           password=CFG_Z39_SERVER[server].get("password", None))
                    conn.databaseName = CFG_Z39_SERVER[server]["databasename"]
                    conn.preferredRecordSyntax = CFG_Z39_SERVER[server]["preferredRecordSyntax"]
                    value = argd["search"].replace("-", "") if argd["search_type"] == "ISBN" else \
                        argd["search"]
                    query = zoom.Query('CCL', u'{0}="{1}"'.format(
                        self._request_type_dict[argd["search_type"]], value))
                    body_content += ""
                    try:
                        server_answer = conn.search(query)
                        if len(server_answer) < 100:
                            nb_to_browse = len(server_answer)
                        else:
                            nb_to_browse = 100
                            errors[server]["remote"].append(
                                "The server {0} returned too many results. {1}/{2} are printed.".format(
                                    server, nb_to_browse, len(server_answer)))
                        for result in server_answer[0:nb_to_browse]:
                            res.append({"value": result, "provider": server})
                    except zoom.Bib1Err as e:
                        errors[server]["remote"].append("{0}".format(e))
                        err = True
                    conn.close()
                except Exception as e:
                    register_exception()
                    errors[server]["internal"].append("{0}".format(e))
                    if conn:
                        conn.close()

            p_err = False
            warnings = '<div class="error">'
            for server in errors:
                if errors[server]["internal"] or errors[server]["remote"]:
                    warnings += "<b>{0}</b><ul>".format(server)
                    for error in errors[server]["internal"]:
                        warnings += "<li>(internal) {0}</li>".format(error)
                    for error in errors[server]["remote"]:
                        warnings += "<li>(remote) {0}</li>".format(error)
                    warnings += "</ul>"
                    p_err = True
            if p_err:
                body_content += "{0}</div>".format(warnings)

            if res:

                body_content += "<table id='result_area' class='fullwidth  tablesorter'>"
                body_content += "<tr><th class='bibz39_titles_th' >Title</th><th class='bibz39_sources_th'>Authors</th><th>Publisher</th><th class='bibz39_sources_th'>Source</th><th><div class='bibz39_button_td'>View XML</div></th><th><div class='bibz39_button_td'>Import</div></th></tr>"

                for identifier, rec in enumerate(res):
                    list_of_record.append(
                        create_record(
                            self.interpret_string(zmarc.MARC(
                                rec["value"].data, strict=0).toMARCXML()))[0])
                    title = ''
                    authors = ''
                    publishers = ''

                    if "100" in list_of_record[identifier]:
                        for author in list_of_record[identifier]["100"]:
                            for tag in author[0]:
                                if tag[0] == 'a':
                                    if authors != "":
                                        authors += " / " + tag[1].strip(",;.")
                                    else:
                                        authors += tag[1].strip(",;.") + " "
                    if "700" in list_of_record[identifier]:
                        for author in list_of_record[identifier]["700"]:
                            for tag in author[0]:
                                if tag[0] == 'a':
                                    if authors != "":
                                        authors += " / " + tag[1].strip(",;.")
                                    else:
                                        authors += tag[1].strip(",;.") + " "
                    if "260" in list_of_record[identifier]:
                        for publisher in list_of_record[identifier]["260"][0][0]:
                            publishers += publisher[1] + " "
                    if "245" in list_of_record[identifier]:
                        for title_constituant in list_of_record[identifier]["245"][0][0]:
                            title += title_constituant[1] + " "

                    body_content += "<tr><td><div class='bibz39_titles' onclick='showxml({6})'>{0}<div><td>{4}</td><td>{5}</td</td><td><div>{2}</div></td><td><div class='bibz39_button_td'>{3}</div></td><td><div class='bibz39_button_td'>{1}</div></td></tr>".format(
                        title,
                        '<form method="post" action="/admin2/bibz39/"><input type="hidden"  name="marcxml"  value="{0}"><input type="submit" value="Import" /></form>'.format(
                            cgi.escape(record_xml_output(list_of_record[identifier])).replace(
                                "\"", "&quot;").replace("\'", "&quot;")),
                        rec["provider"],
                        '<button onclick="showxml({0})">View</button>'.format(identifier),
                        authors, publishers, identifier)
                body_content += "</table>"
                body_content += '<script type="text/javascript">'
                body_content += "var gAllMarcXml= {"
                for i, rec in enumerate(list_of_record):
                    body_content += "{0}:{1},".format(i, json.dumps(record_xml_output(rec)))
                body_content += "};"
                body_content += '</script>'

            else:
                if not err:
                    body_content += "<p class='bibz39_button_td spinning_wheel'> No result</p>"

            body_content += '<div id="dialog-message" title="XML Preview"></div></div>'

        return page(title="Z39.50 Search",
                    body=body_content,
                    errors=[],
                    warnings=[],
                    metaheaderadd=get_head(),
                    req=req)

    def interpret_string(self, data):
        try:
            list_data = data.split("\n")
            for i in range(len(list_data)):
                list_data[i] = zmarc.MARC8_to_Unicode().translate(list_data[i])
            return "\n".join(list_data)
        except:
            return data

    def __call__(self, req, form):
        """Redirect calls without final slash."""
        redirect_to_url(req, '%s/admin2/bibz39/' % CFG_SITE_SECURE_URL)

    def generate_request_form(self, argd):
        html = ""
        html += """
        <div class='server_area'>Search in:<div class="bibz39_servers">"""

        for server in CFG_Z39_SERVER.keys():
            if (not argd["server"] and "default" in CFG_Z39_SERVER[server] and
                    CFG_Z39_SERVER[server][
                        "default"]) or server in argd["server"]:
                html += "<div><input form='main_form' type='checkbox' name='server' value='{0}' checked>{0}</div>".format(
                    server)
            else:
                html += "<div><input form='main_form' type='checkbox' name='server' value='{0}'>{0}</div>".format(
                    server)
        html += """</div></div><div id='middle_area'>
        <form id="main_form" method="post" action="/admin2/bibz39/">
        <div id='search_form'>
        <div id='radiobuttons'>"""

        if argd["search_type"]:
            for req_type in self._request_type_dict:
                html += """<input type="radio" name="search_type" value="{0}"{1}> {0}""".format(
                    req_type, "checked" if req_type == argd["search_type"] else "")
        else:
            for req_type in self._request_type_dict:
                html += """<input type="radio" name="search_type" value="{0}"{1}> {0}""".format(
                    req_type, "checked" if req_type == "ISBN" else "")

        html += """</div>
        <input type="text" onkeydown="enterKeyLookUp(event)" name="search" id="search" value="{0}" />
        <button type="button" onclick="spinning(event)" /> Search</button>
        </div>
        </form>""".format(argd["search"])

        return html


def get_head():
    """
    Get all required scripts
    """
    js_scripts = """
<link rel="stylesheet" href="%(site_url)s/img/font-awesome.min.css">
<link rel="stylesheet" href="%(site_url)s/img/jquery-ui.css">
<link rel="stylesheet" href="%(site_url)s/css/bibz39.css">
<script type="text/javascript" src="%(site_url)s/js/jquery-ui.min.js">
</script>
<script type="text/javascript" src="%(site_url)s/js/bibz39.js">
</script>
                 """ % {'site_url': CFG_SITE_URL}
    return js_scripts
