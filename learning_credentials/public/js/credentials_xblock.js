function CredentialsXBlock(runtime, element) {
    function generateCredential(event) {
        const button = event.target;
        const credentialType = $(button).data('credential-type');
        const handlerUrl = runtime.handlerUrl(element, 'generate_credential');

        $.post(handlerUrl, JSON.stringify({ credential_type: credentialType }))
          .done(function(data) {
              const messageArea = $(element).find('#message-area-' + credentialType);
              if (data.status === 'success') {
                  messageArea.html('<p style="color:green;">Certificate generation initiated successfully.</p>');
              } else {
                  messageArea.html('<p style="color:red;">' + data.message + '</p>');
              }
          })
          .fail(function() {
              const messageArea = $(element).find('#message-area-' + credentialType);
              messageArea.html('<p style="color:red;">An error occurred while processing your request.</p>');
          });
    }

    $(element).find('.generate-credential').on('click', generateCredential);
}
