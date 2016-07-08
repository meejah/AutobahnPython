from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner

class MyComponent(ApplicationSession):
    def __init__(self, config=None):
        ApplicationSession.__init__(self, config)
        print("component created")

    def onConnect(self):
        print("transport connected")
        self.join(self.config.realm)

    def onChallenge(self, challenge):
        print("authentication challenge received")

    def onJoin(self, details):
        print("session joined: {}".format(details))

    def onLeave(self, details):
        print("session left: {}".format(details))

    def onDisconnect(self):
        print("transport disconnected")

runner = ApplicationRunner(url=u"ws://localhost:8080/ws", realm=u"realm1")
runner.run(MyComponent)
