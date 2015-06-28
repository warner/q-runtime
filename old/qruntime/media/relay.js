
function doAPI(method, args, callback) {
    $.ajax({type: "POST",
            url: "/relay/api",
            contentType: "text/json", // what we send
            data: JSON.stringify({method: method, args: args}),
            // data: {a:foo,b:bar} makes .ajax to serialize like "a=foo&b=bar"
            dataType: 'json', // what we expect, and how to parse it
            success: callback });
};

function fill(method, element) {
    $(element).text("updating...");
    doAPI(method, {}, function(data) { $(element).text(data.text); });
};

function client_row(cl) {
    var row = d3.select(this).append("ul");
    row.append("li").text("from: "+cl.from);
    row.append("li").text("since: "+cl.connected);
    row.append("li").text("messages received: "+cl.rx);
    row.append("li").text("messages sent: "+cl.tx);
    row.append("li").text("subscribing to: "+cl.subscriptions);
};

function fill_clients(method, element) {
    var root = $(element);
    root.empty();
    root.append($("<li/>").text("updating.."));
    doAPI(method, {}, function(data)
          {
              root.empty();
              var l = d3.select("#clients");
              var rows = l.selectAll("li").data(data);
              rows.exit().remove();
              var newrows = rows.enter().append("li")
                  .text(function(d,i) {return "client "+i;})
                  .attr("class", "clients");
              newrows.each(client_row);
          });
};


$(function() {
      $("#tabs").tabs({selected: -1,
                       show: function(event, ui)
                       {
                           if (ui.index == 0) {
                               fill("webport", "#webport");
                               fill("relayport", "#relayport");
                           } else if (ui.index == 1) {
                               fill_clients("clients", "#clients");
                           }
                           return true;
                       }
                       });
});
