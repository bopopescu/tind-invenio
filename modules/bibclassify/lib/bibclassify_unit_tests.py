# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2010, 2011, 2013 CERN.
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

"""
Test suite for BibClassify module - this unit-test is actually abusing
an idea of unit-testing. Some of the test require a lot of time (several
seconds) to run: they download files, process fulltexts, rebuild cache etc
[rca]

This module is STANDALONE SAFE
"""

import sys

from invenio.testutils import InvenioTestCase
import tempfile
import cStringIO
import os
import time
import stat
import shutil

from invenio import bibclassify_config as bconfig
from invenio.testutils import make_test_suite, run_test_suite, nottest
from invenio import config
from invenio import bibclassify_ontology_reader

log = bconfig.get_logger("bibclassify.tests")

# do this only if not in STANDALONE mode
bibclassify_daemon = dbquery = None
if not bconfig.STANDALONE:
    from invenio import bibdocfile


class BibClassifyTestCase(InvenioTestCase):
    """ Abusive test suite - the one that takes sooooo long """

    def setUp(self):
        """Initialize stuff"""
        #self.tmpdir = invenio.config.CFG_TMPDIR
        self.original_tmpdir = config.CFG_TMPDIR
        config.CFG_TMPDIR = tempfile.gettempdir()

        self.oldstdout = sys.stdout
        self.oldstderr = sys.stderr
        self.stdout = None
        self.stderr = None

        self.taxonomy_name = "test"

        self.log_level = bconfig.logging_level
        bconfig.set_global_level(bconfig.logging.CRITICAL)

    def tearDown(self):
        config.CFG_TMPDIR = self.original_tmpdir
        if self.stdout:
            self.unredirect()
        bconfig.set_global_level(self.log_level)

    def redirect(self):
        # just for debugging in Eclipse (to see messages printed)
        if 'stdout' in sys.argv:
            self.stdout = sys.stdout
            self.stderr = sys.stderr
        else:
            self.stdout = cStringIO.StringIO()
            self.stderr = cStringIO.StringIO()

        sys.stdout = self.stdout
        sys.stderr = self.stderr

    def unredirect(self):
        sin, serr = '', ''
        if self.stdout:
            self.stdout.flush()
            self.stdout.seek(0)
            sin = self.stdout.read()
            self.stderr.flush()
            self.stderr.seek(0)
            serr = self.stderr.read()

            self.stdout.close()
            self.stderr.close()
        self.stdout = None
        self.stderr = None
        sys.stdout = self.oldstdout
        sys.stderr = self.oldstderr

        return sin, serr


    @nottest
    def get_test_file(self, recid, type='Main', format='pdf'):

        br = bibdocfile.BibRecDocs(recid)
        bibdocs = br.list_bibdocs(type)
        # we grab the first
        for b in bibdocs:
            x = b.get_file(format)
            if x:
                return x.get_full_path(), x.get_url()



class BibClassifyTest(BibClassifyTestCase):


    def test_rebuild_cache(self):
        """bibclassify - test rebuilding cache (takes long time)"""

        info = bibclassify_ontology_reader._get_ontology(self.taxonomy_name)

        if info[0]:
            cache = bibclassify_ontology_reader._get_cache_path(info[0])

            if os.path.exists(cache):
                ctime = os.stat(cache)[stat.ST_CTIME]
            else:
                ctime = -1

            rex = bibclassify_ontology_reader.get_regular_expressions(self.taxonomy_name, rebuild=True)

            self.assertTrue(os.path.exists(cache))
            ntime = os.stat(cache)[stat.ST_CTIME]

            self.assertTrue((ntime > ctime))
        else:
            raise Exception("Taxonomy wasn't found")


    def test_cache_accessibility(self):
        """bibclassify - test cache accessibility/writability"""

        # we will do tests with a copy of test taxonomy, in case anything goes wrong...
        orig_name, orig_taxonomy_path, orig_taxonomy_url = bibclassify_ontology_reader._get_ontology(self.taxonomy_name)

        taxonomy_path = orig_taxonomy_path.replace('.rdf', '.copy.rdf')
        taxonomy_name = self.taxonomy_name + '.copy'

        shutil.copy(orig_taxonomy_path, taxonomy_path)
        assert(os.path.exists(taxonomy_path))

        name, taxonomy_path, taxonomy_url = bibclassify_ontology_reader._get_ontology(taxonomy_name)

        cache = bibclassify_ontology_reader._get_cache_path(os.path.basename(taxonomy_path))


        if not name:
            raise Exception("Taxonomy wasn't found")

        if os.path.exists(cache):
            os.remove(cache)

        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)
        assert(os.path.exists(cache))

        log.error('Testing corrupted states, please ignore errors...')

        # set cache unreadable
        os.chmod(cache, 000)
        try: bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)
        except: pass
        else: raise Exception('cache chmod to 000 but no exception raised')

        # set cache unreadable and test writing
        os.chmod(cache, 000)
        try: bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)
        except: pass
        else: raise Exception('cache chmod to 000 but no exception raised')

        # set cache unreadable but don't care for it
        os.chmod(cache, 000)
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=True)
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=True)

        # set cache readable and test writing
        os.chmod(cache, 600)
        try: bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)
        except: pass
        else: raise Exception('cache chmod to 600 but no exception raised')

        # set cache writable only
        os.chmod(cache, 200)
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)


        # set cache readable/writable but corrupted (must rebuild itself)
        os.chmod(cache, 600)
        os.remove(cache)
        open(cache, 'w').close()
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)


        # set cache readable/writable but corrupted (must rebuild itself)
        open(cache, 'w').close()
        try:
            try:
                os.rename(taxonomy_path, taxonomy_path + 'x')
                open(taxonomy_path, 'w').close()
                bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)
            except:
                pass
        finally:
            os.rename(taxonomy_path+'x', taxonomy_path)

        # make cache ok, but corrupt source
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)

        try:
            try:
                os.rename(taxonomy_path, taxonomy_path + 'x')
                open(taxonomy_path, 'w').close()
                time.sleep(.1)
                os.utime(cache, (time.time() + 100, time.time() + 100))  #touch the taxonomy to be older
                bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)
            except:
                os.rename(taxonomy_path+'x', taxonomy_path)
                raise Exception('Cache exists and is ok, but was ignored')
        finally:
            os.rename(taxonomy_path+'x', taxonomy_path)

        # make cache ok (but old), and corrupt source
        bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=True, no_cache=False)
        try:
            try:
                os.rename(taxonomy_path, taxonomy_path + 'x')
                open(taxonomy_path, 'w').close()
                bibclassify_ontology_reader.get_regular_expressions(taxonomy_name, rebuild=False, no_cache=False)
            except:
                pass
        finally:
            os.rename(taxonomy_path+'x', taxonomy_path)

        log.error('...testing of corrupted states finished.')

        name, taxonomy_path, taxonomy_url = bibclassify_ontology_reader._get_ontology(taxonomy_name)
        cache = bibclassify_ontology_reader._get_cache_path(name)
        os.remove(taxonomy_path)
        os.remove(cache)

    def xtest_ingest_taxonomy_by_url(self):
        pass

    def xtest_ingest_taxonomy_by_name(self):
        pass

    def xtest_ingest_taxonomy_by_path(self):
        pass

    def xtest_ingest_taxonomy_db_name(self):
        pass

    def xtest_ouput_modes(self):
        pass

    def xtest_get_single_keywords(self):
        """test the function returns {<keyword>: [ [spans...] ] }"""

    def xtest_get_composite_keywords(self):
        """test the function returns {<keyword>: [ [spans...], [correct component counts] ] }"""





def suite(cls=BibClassifyTest):
    import unittest
    tests = []
    for x in sys.argv[1:]:
        if x[0:4] == 'test':
            tests.append(x)
    if len(tests) < 1:
        raise Exception('You must specify tests to run')

    return unittest.TestSuite(map(cls, tests))

if 'custom' in sys.argv:
    TEST_SUITE = suite(BibClassifyTest)
else:
    TEST_SUITE = make_test_suite(BibClassifyTest)


if __name__ == '__main__':
    run_test_suite(TEST_SUITE)
