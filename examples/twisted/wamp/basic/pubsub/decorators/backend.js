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

   var counter = 0;

   setInterval(function () {
      console.log("publishing to topic 'com.myapp.topic1': " + counter);
      session.publish('com.myapp.topic1', [counter]);
      session.publish('com.myapp.topic2', ["Hello world."]);
      counter += 1;
   }, 1000);
};

connection.open();
