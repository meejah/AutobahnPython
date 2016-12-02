#
# Note: this is set up in the config.json for the router; see
# examples/router/.crossbar/config.json and look for the component
# configured as "type": "function"
#

def on_join(session, details):
    print("functional join", session, details)

def on_leave(session, details):
    print("functional leave", session, details)

def on_connect(session, transport):
    print("functional connect", session, transport)

def on_disconnect(session):
    print("functional disconnect", session)
