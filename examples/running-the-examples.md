# Running the Examples

## Setting up a Router

To run the following examples, you need a WAMP router.

By default, **all examples are set up to use a public demonstration router** at `wss://demo.crossbar.io/ws`.

If you wish to run your own, local, router see [Running Crossbar Locally] below. This avoids sending Autobahn traffic outside your network.


## Creating a virtualenv

If you do not yet have a `virtualenv` to run the examples with, you can do something like:

```shell
cd ./autobahn-clone/
virtualenv venv-autobahn
source venv-autobahn/bin/activate
pip install -e ./
```

For all the examples, we presume that you are in the `./examples` directory of your autobahn clone, and that the virtualenv in which you've installed Autobahn is activated. If you're running your own Crossbar, it runs from `./examples/router` in its own virtualenv.

The examples usually contain two components:

 * frontend
 * backend

Each component is (usually) provided in two languages:

 * Python
 * JavaScript

The JavaScript version can run on the browser or in NodeJS.

To run an example, you can have two (or three) terminal sessions open with:

 1. frontend
 2. backend
 3. the router (e.g. `crossbar`)

You can also run the frontend/backend in the same shell by putting one in the background. This makes tbe examples less clear, however:

```shell
python twisted/wamp/basic/pubsub/basic/frontend.py &
python twisted/wamp/basic/pubsub/basic/backend.py
```

Some **things to try**: open a new terminal and run a second frontend;  leave the backend running for a while and then run the frontend; disconnect a frontend and reconnect (re-run) it; mix and match the examples (e.g. twisted/wamp/basic/pubsub/basic/backend.py with twisted/wamp/basic/pubsub/decorators/frontend.py) to see how the topic URIs interact.


## Running Crossbar Locally

If you want to use your own local [Crossbar](http://crossbar.io) instance you must have a Python2-based virtualenv and `pip install crossbar` in it. See also [crossbar.io's platform-specific installation instructions](http://crossbar.io/docs/Local-Installation/) as you may need to install some native libraries as well.

Once you have crossbar installed, use the provided router configuration in `examples/router/.crossbar/config.json`. Starting your router is then:

```shell
cd examples/router
crossbar start
```

There should now be a router now listening on `localhost:8080` so you can change the URI in all the demos to `ws://localhost:8080/ws` or set the environment variable `AUTOBAHN_DEMO_ROUTER=ws://localhost:8080/ws` Obviously, this environment variable isn't used by in-browser JavaScript so you'll have to change .js files by hand.

If you are running the router successfully, you should see a Crossbar page at `http://localhost:8080/`. We've added enough configuration to serve the HTML, JavaScript and README files from all the examples; you should see a list of links at the page.


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
