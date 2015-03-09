# WAMP Programming Examples

## Examples

1. RPC
  * [Arguments](rpc/arguments)
  * [Complex](rpc/complex)
  * [Decorators](rpc/decorators)
  * [Errors](rpc/errors)
  * [Options](rpc/options)
  * [Progress](rpc/progress)
  * [Slow Square](rpc/slowsquare)
  * [Time Service](rpc/timeservice)
2. PubSub
  * [Basic](pubsub/basic)
  * [Complex](pubsub/complex)
  * [Decorators](pubsub/decorators)
  * [Options](pubsub/options)
  * [Unsubscribe](pubsub/unsubscribe)


## How to run

To run the following examples, you need a WAMP router. By default,
they are using the public router `wss://demo.crossbar.io/ws` If you do
not yet have a `virtualenv`, you can do something like:

```shell
cd ./autobahn-clone/
virtualenv venv-autobahn
source venv-autobahn/bin/activate
pip install -e ./
```

If you would prefer not to generate traffic outside your network, you
should run your own WAMP Router, such as [Crossbar.io](http://crossbar.io):

```shell
pip install crossbar
mkdir /tmp/demo-router
cd /tmp/demo-router/
crossbar init
crossbar start
```

You will then need to change instances of `wss://demo.crossbar.io/ws`
to your URL (by default, if you ran the above, this will be
`ws://localhost:8080/ws`) *OR* set the environment variable
`AUTOBAHN_DEMO_URL=ws://localhost:8080/ws`

If running the router was successful, you should see a Crossbar 404
page at http://localhost:8080/

The examples usually contain two components:

 * frontend
 * backend

Each component is provided in two languages:

 * Python
 * JavaScript

The JavaScript version can run on the browser or in NodeJS.

To run an example, you can have three terminal sessions open with:

 1. router (e.g. `crossbar` as above)
 2. frontend
 3. backend

E.g. the Python examples can be run, if you're already running the
above router somehwere:

```shell
python pubsub/basic/frontend.py &
python pubsub/basic/backend.py
```

Try runnnig two frontends, or leaving the backend running for a while
and then run the frontend.


## Hosting

Crossbar.io is a WAMP router that can also act as a host for WAMP application components. E.g. to let Crossbar.io host a backend application component, you can use a node configuration like this:

```javascript

{
   "controller": {
   },
   "workers": [
      {
         "type": "router",
         "options": {
            "pythonpath": ["f:\\scm\\tavendo\\autobahn\\AutobahnPython\\examples\\twisted\\wamp\\basic"]
         },
         "realms": [
            {
               "name": "realm1",
               "roles": [
                  {
                     "name": "anonymous",
                     "permissions": [
                        {
                           "uri": "*",
                           "publish": true,
                           "subscribe": true,
                           "call": true,
                           "register": true
                        }
                     ]
                  }
               ]
            }
         ],
         "components": [
            {
               "type": "class",
               "classname": "pubsub.complex.backend.Component",
               "realm": "realm1"
            }
         ],
         "transports": [
            {
               "type": "web",
               "endpoint": {
                  "type": "tcp",
                  "port": 8080
               },
               "paths": {
                  "/": {
                     "type": "static",
                     "directory": ".."
                  },
                  "ws": {
                     "type": "websocket"
                  }
               }
            }
         ]
      }
   ]
}
```