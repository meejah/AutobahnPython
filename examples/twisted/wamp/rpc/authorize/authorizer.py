from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.wamp import ApplicationSession


class MyAuthorizer(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):
       print("MyAuthorizer.onJoin({})".format(details))
       try:
           yield self.register(self.authorize, u'com.example.authorize')
           yield self.register(self.scram_authorize, u'com.example.scram_auth')
           print("MyAuthorizer: authorizer registered")
       except Exception as e:
           print("MyAuthorizer: failed to register authorizer procedure ({})".format(e))
           raise

    def scram_authorize(self, realm, authid, details):
        print("dynamic SCRAM authorize: authid={}, realm={}".format(authid, realm))
        if authid == u"carol" and realm == u"crossbardemo":
            # this corresponds to client secret "p4ssw0rd"
            return {
                u"role": "authenticated",
                u"memory": 512,
                u"kdf": "argon2id-13",
                u"iterations": 4096,
                u"salt": "accaa46d16de59a12db736c8ed2cc90c",
                u"stored-key": "6524cf40c287834819a9c46a591f75be42d67f253aec73fe97d55736d1a928bd",
                u"server-key": "877b77c9fb3e12c13948812d9db909ceb794de9a7ec8a0c025f57ad8dff24ab8"
            }
        return False

    def authorize(self, details, uri, action, options):
        print("MyAuthorizer.authorize(uri='{}', action='{}', options='{}')".format(uri, action, options))
        print("options:")
        for k, v in options.items():
            print("  {}: {}".format(k, v))
        if False:
            print("I allow everything.")
        else:
            if uri == u'com.foo.private':
                return False
            if options.get(u"match", "exact") != u"exact":
                print("only exact-match subscriptions allowed")
                return False
        return True
