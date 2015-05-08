try {
   var autobahn = require('autobahn');
} catch (e) {
   // when running in browser, AutobahnJS will
   // be included without a module system
}

var connection = new autobahn.Connection({
   url: 'wss://demo.crossbar.io/ws',
   realm: 'crossbardemo'}
);

connection.onopen = function (session) {

   var received = 0;

   function onevent1(args) {
      console.log("Got event:", args[0]);
      received += 1;
      if (received > 5) {
         console.log("Closing ..");
         connection.close();
      }
   }

   session.subscribe('com.myapp.topic1', onevent1);
};

connection.open();
