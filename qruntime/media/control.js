
function doAPI(method, args, callback) {
    $.ajax({type: "POST",
            url: "/control/api",
            contentType: "text/json", // what we send
            data: JSON.stringify({token: token, method: method, args: args}),
            // data: {a:foo,b:bar} makes .ajax to serialize like "a=foo&b=bar"
            dataType: 'json', // what we expect, and how to parse it
            success: callback });
};

function fill(method, element) {
    $(element).text("updating...");
    doAPI(method, {}, function(data) { $(element).text(data.text); });
};

function fill_val(method, element) {
    doAPI(method, {}, function(data) { $(element).val(data.text); });
};

function hshow(element) {
    $(element).show("slide", {direction: "horizontal"});
};
function hhide(element) {
    $(element).hide("slide", {direction: "horizontal"});
};
function htoggle(element) {
    $(element).toggle("slide", {direction: "horizontal"});
};

function sendMessage(event) {
    console.log("sendMessage");
    var args = {to: $("#send-to").val(),
                args: $("#send-args").val()
               };
    doAPI("sendMessage", args, function(){alert("Sent!");});
};

function profileSetName(event) {
    var name = $("#profile-name-input").val();
    doAPI("profile-set-name", {"name": name});
    $("#profile-name").text(name);
};

function profileFillIcon() {
    doAPI("profile-get-icon", {},
          function(data) {
              $("#profile-icon").attr("src", data["icon-data"]);
              });
};

function profileSetIcon(iconfile) {
    //var fileurl = window.URL.createObjectURL(iconfile);
    //console.log("URL", fileurl, iconfile.size, iconfile.type);
    var reader = new FileReader();
    reader.onload = function(e) {
        var data = e.target.result;
        doAPI("profile-set-icon", {"icon-data": data}, profileFillIcon);
    };
    reader.readAsDataURL(iconfile);
};

function profileDropIcon(e, ui) {
    e.stopPropagation();
    e.preventDefault();
    profileSetIcon(e.originalEvent.dataTransfer.files[0]);
    return false;
};

function selectAddressBookEntry(e) {
    var d = $(this).data("entry");
    $("#address-book-petname").text(d.petname);
    $("#address-book-icon").attr("src", d.icon_data);
    $("#address-book-selfname").text(d.selfname);
    $("#address-book-their-pubkey").text(d.their_pubkey);
    return false;
};

function deleteAddressBookEntry(e) {
    var d = $(this).parent().data("entry");
    doAPI("deleteAddressBookEntry", {petname: d.petname});
};

function getAddressBook() {
    doAPI("getAddressBook", {},
          function (data) {
              var book = $("#address-book");
              book.empty();
              for (var i=0; i<data.length; i++) {
                  var d = data[i];
                  var entry = $("<li>");
                  entry.text(d.petname);
                  entry.data("entry", d);
                  entry.on("click", selectAddressBookEntry);
                  book.append(entry);
                  /*
                  var entry = $("#templates .address-book-entry").clone();
                  entry.find(".name").text(d.petname);
                  entry.find(".icon").attr("src", d.icon_data);
                  entry.data("entry", d);
                  entry.find(".delete").on("click", deleteAddressBookEntry);
                  book.append(entry); */
              }
          });
    return false;
};


function togglePendingInvitations() {
    $("#pending-invitations").slideToggle();
};

function cancelInvitation(invite) {
    doAPI("cancelInvitation", invite, getPendingInvitations);
};

function getPendingInvitations() {
    doAPI("getOutboundInvitations", {},
          function (data) {
              $("#count-pending-invitations").text(data.length);
              var pending = $("#pending-invitations ul");
              pending.empty();
              for (var i=0; i<data.length; i++) {
                  var d = data[i];
                  var h = $('<li><a href="#"></a></li>')
                      .appendTo(pending)
                  ;
                  h.find("a")
                      .text(d.petname)
                      .data("invite-number", i)
                      .on("click",
                          function() {var i = $(this).data("invite-number");
                                      $("#pending-invite-"+i).slideToggle();})
                  ;
                  var details = $('<ul/>')
                      .appendTo(h)
                      .hide()
                      .attr("id", "pending-invite-"+i)
                  ;
                  details.append($('<li/>').text("Invitation Code: "+d.code));
                  details.append($('<li/>').text("Sent: "+d.sent));
                  details.append($('<li/>').text("Expires: "+d.expires));
                  details.append($('<li/>')
                                 .html('<a href="#">cancel</a>')
                                 .find("a")
                                 .data("invite", d)
                                 .on("click",
                                     function() {var d = $(this).data("invite");
                                                 cancelInvitation(d);})
                                 );
              }
              if (data.length) {
                  $("#toggle-pending-invitations").slideDown();
                  $("#pending-invite-0").show();
              } else {
                  $("#toggle-pending-invitations").slideUp();
              }
          });
};

function startInvitation(event) {
    doAPI("startInvitation", {});
    $("#invite-prepare-invitation").slideDown(500,
                                             function() {
                                                 $("#invite").slideUp(500);
                                                 });
    $("#invite-to").focus(); // TODO: make 'return' trigger the button
};

function sendInvitation(event) {
    var args = { name: $("#invite-to").val() };
    doAPI("sendInvitation", args, getPendingInvitations);
    $("#pending-invitations").slideDown();
    $("#pending-invite-0").slideDown();
    $("#invite-prepare-invitation").slideUp();
    setTimeout(function() { $("#invite").slideDown("slow"); }, 5000);
};

function acceptInvitation(event) {
    var args = { name: $("#invite-from").val(),
                 code: $("#invite-code").val() };
    $("#invite-from").val("");
    $("#invite-code").val("");
    doAPI("acceptInvitation", args,
          function () {
              $("#tabs").tabs("select", 2);
              });
};

$(function() {
      $("#tabs").tabs({selected: 0,
                       show: function(event, ui)
                       {
                           if (ui.index == 0) {
                               fill("webport", "#webport");
                               fill("url", "#url");
                               fill("vatid", "#vatid");
                           }
                           return true;
                       }
                       });
      $("#send-message").on("click", sendMessage);
});
