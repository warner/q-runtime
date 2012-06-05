const http = require("http");

function handle(request, response) {
    response.writeHead(200, {'Content-Type': 'text/plain'});
    response.end("hello\n");
};

var s = http.createServer(handle).listen(10001);
console.log("Server running at http://localhost:1001/");
