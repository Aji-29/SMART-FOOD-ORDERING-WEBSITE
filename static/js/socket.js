$(document).ready(function() {
        // Connect to the Socket.IO server
        var socket = io.connect('http://' + document.domain + ':' + location.port);

        // Verify connection and listen for the 'order_delivered' event
        socket.on('connect', function() {
            console.log('Connected to Socket.IO server');

            // Optionally join a specific room
            // Replace `user_id` with the actual user ID
            socket.emit('join', 'user_id');
        });

        // Listen for the 'order_delivered' event
        socket.on('order_delivered', function(data) {
            console.log("Order Delivered Event Triggered", data);
            alert('Order ' + data.order_id + ' has been delivered!');
            // Update the UI or trigger other actions here
        });

});