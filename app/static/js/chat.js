input.addEventListener('input', () => {
    socket.emit('typing', {
        room,
        sender_id: currentUserId,
        receiver_id: receiverId
    });
});
