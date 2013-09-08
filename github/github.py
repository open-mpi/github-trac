from trac.core import *
from trac.config import Option
from trac.web.api import IRequestFilter, IRequestHandler, _RequestArgs
import urllib2

from hook import CommitHook

import simplejson

# GitPython module seems to have a bug showing thread warnings all the time.
# This is really annoying so I make it ignored.
# dikim@cs.indiana.edu (Sep 7, 2013)
with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from git import Git

class GithubPlugin(Component):
    implements(IRequestHandler, IRequestFilter)
    
    
    key = Option('github', 'apitoken', '', doc="""Your GitHub API Token found here: https://github.com/account, """)
    closestatus = Option('github', 'closestatus', '', doc="""This is the status used to close a ticket. It defaults to closed.""")
    browser = Option('github', 'browser', '', doc="""Place your GitHub Source Browser URL here to have the /browser entry point redirect to GitHub.""")
    autofetch = Option('github', 'autofetch', '', doc="""Should we auto fetch the repo when we get a commit hook from GitHub.""")
    branches = Option('github', 'branches', "all", doc="""Restrict commit hook to these branches. """
        """Defaults to special value 'all', do not restrict commit hook""")
    comment_template = Option('github', 'comment_template', "Changeset: {commit[id]}", doc="""This will be appended to your commit message and used as trac comment""")
    repo = Option('trac', 'repository_dir', '', doc="""This is your repository dir""")

    def __init__(self):
        self.hook = CommitHook(self.env, self.comment_template)
        self.env.log.debug("API Token: %s" % self.key)
        self.env.log.debug("Browser: %s" % self.browser)
        self.processHook = False
        self.env.log.debug("Match Request")

    
    # IRequestHandler methods
    def match_request(self, req):
        self.env.log.debug("Match Request: %s, key: %s" % (req.path_info, self.key))
        serve = req.path_info.rstrip('/') == ('/github/%s' % self.key) and req.method == 'POST'
        if serve:
            self.processHook = True
            #This is hacky but it's the only way I found to let Trac post to this request
            #   without a valid form_token
            req.form_token = None

        self.env.log.debug("Handle Request: %s" % serve)
        return serve
    
    def process_request(self, req):
        if self.processHook:
            self.processCommitHook(req)

    # This has to be done via the pre_process_request handler
    # Seems that the /browser request doesn't get routed to match_request :(
    def pre_process_request(self, req, handler):
        if self.browser:
            serve = req.path_info.startswith('/browser')
            self.env.log.debug("Handle Pre-Request /browser: %s" % serve)
            if serve:
                self.processBrowserURL(req)

            serve2 = req.path_info.startswith('/changeset')
            self.env.log.debug("Handle Pre-Request /changeset: %s" % serve2)
            if serve2:
                self.processChangesetURL(req)

        return handler


    def post_process_request(self, req, template, data, content_type):
        return (template, data, content_type)


    def processChangesetURL(self, req):
        self.env.log.debug("processChangesetURL")
        browser = self.browser.replace('/tree/master', '/commit/')
        
        url = req.path_info.replace('/changeset/', '')
        if not url:
            browser = self.browser
            url = ''

        redirect = '%s%s' % (browser, url)
        self.env.log.debug("Redirect URL: %s" % redirect)
        out = 'Going to GitHub: %s' % redirect

        req.redirect(redirect)


    def processBrowserURL(self, req):
        self.env.log.debug("processBrowserURL")
        browser = self.browser.replace('/master', '/')
        rev = req.args.get('rev')
        
        url = req.path_info.replace('/browser', '')
        if not rev:
            rev = ''

        redirect = '%s%s%s' % (browser, rev, url)
        self.env.log.debug("Redirect URL: %s" % redirect)
        out = 'Going to GitHub: %s' % redirect

        req.redirect(redirect)

    def parse_query_string(self, query_string):
        """Parse a query string into a _RequestArgs."""
        args = _RequestArgs()
        for arg in query_string.split('&'):
            nv = arg.split('=', 1)
            if len(nv) == 2:
                (name, value) = nv
            else:
                (name, value) = (nv[0], '')
            name = urllib2.unquote(name.replace('+', ' '))
            if isinstance(name, unicode):
                name = name.encode('utf-8')
            value = urllib2.unquote(value.replace('+', ' '))
            if not isinstance(value, unicode):
                value = unicode(value, 'utf-8')
            if name in args:
                if isinstance(args[name], list):
                    args[name].append(value)
                else:
                    args[name] = [args[name], value]
            else:
                args[name] = value
        return args
        

    def processCommitHook(self, req):
        self.env.log.debug("processCommitHook")
        status = self.closestatus
        if not status:
            status = 'closed'

        data = req.args.get('payload')
        branches = (self.parse_query_string(req.query_string).get('branches') or self.branches).split(',')
        self.env.log.debug("Using branches: %s", branches)

        if data:
            jsondata = simplejson.loads(data)
            ref = jsondata['ref'].split('/')[-1]

            if ref in branches or 'all' in branches:
                for i in jsondata['commits']:
                    self.hook.process(i, status, jsondata)
            else:
                self.env.log.debug("Not running hook, ref %s is not in %s", ref, branches)

        if self.autofetch:
            repo = Git(self.repo)

            try:
              repo.execute(['git', 'fetch'])
            except:
              self.env.log.debug("git fetch failed!")


