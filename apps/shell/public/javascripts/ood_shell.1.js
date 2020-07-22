
// Object that defines a terminal element
function OodShell(element, url, prefs) {
  this.element = element;
  this.url     = url;
  this.prefs   = prefs || {};
  this.socket  = null;
  this.term    = null;
  this.connectionAttemptsSent = 0;
  this.connectionAttempsRecieved = 0;
  this.connectionInterval = null;
}

OodShell.prototype.createTerminal = function () {
  this.socket           = new ReconnectingWebSocket(this.url, null, {reconnectInterval: 1000});
  this.socket.onopen    = this.runTerminal.bind(this);
  this.socket.onmessage = this.getMessage.bind(this);
  this.socket.onclose   = this.closeTerminal.bind(this);
};

OodShell.prototype.runTerminal = function () {
  var that = this;
  showState("", false);
  this.connectionInterval = setInterval(function(){that.checkConnection(that.socket)}, 1000);
  // Set backing store that hterm uses to read/write preferences
  hterm.defaultStorage = new lib.Storage.Memory();

  // Create an instance of hterm.Terminal
  this.term = new hterm.Terminal();

  // Set preferences for terminal
  for (var k in this.prefs) {
    this.term.prefs_.set(k, this.prefs[k]);
  }

  // Handler that fires when terminal is initialized and ready for use
  this.term.onTerminalReady = function () {
    // Create a new terminal IO object and give it the foreground.
    // (The default IO object just prints warning messages about unhandled
    // things to the JS console.)
    var io = this.io.push();

    // Set up event handlers for io
    io.onVTKeystroke    = that.onVTKeystroke.bind(that);
    io.sendString       = that.sendString.bind(that);
    io.onTerminalResize = that.onTerminalResize.bind(that);

    // Capture all keyboard input
    this.installKeyboard();
  };
  
  // Patch cursor setting
  this.term.options_.cursorVisible = true;

  // Connect terminal to sacrificial DOM node
  this.term.decorate(this.element);

  // Warn user if he/she unloads page
  window.onbeforeunload = function() {
    return 'Leaving this page will terminate your terminal session.';
  };

  this.socket.onclose = function (ev) {
    showState("Attempting Reconnection", true);
    clearInterval(that.connectionInterval);
    this.connectionInterval = null;
  }

  this.socket.onopen = function (ev) {
    showState("", false);
    this.connectionInterval = setInterval(function(){that.checkConnection(that.socket)}, 3000);
  }

    this.socket.onerror = function (ev) {
    showState("Attempting Reconnection", true);
  }
};

OodShell.prototype.getMessage = function (ev) {
  var that = this;
  if (ev.data === "heartbeat") {
    if (document.getElementById('state').classList.contains("connecting-state")) {
      showState("", false);
      this.connectionInterval = setInterval(function(){that.checkConnection(that.socket)}, 1000);
    }
    this.connectionAttempsRecieved++;
    return;
  }
  this.term.io.print(ev.data);
}

OodShell.prototype.closeTerminal = function (ev) {
  var errorDiv;

  // Do not need to warn user if he/she unloads page
  window.onbeforeunload = null;

  // Inform user they lost connection
  if ( this.term === null ) {
    errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.innerHTML = 'Failed to establish a websocket connection. Be sure you are using a browser that supports websocket connections.';
    this.element.appendChild(errorDiv);
  } else {
    showState("Attempting Reconnection", true);
  }
}

OodShell.prototype.onVTKeystroke = function (str) {
  // Do something useful with str here.
  // For example, Secure Shell forwards the string onto the NaCl plugin.
  this.socket.send(JSON.stringify({
    input: str
  }));
};

OodShell.prototype.checkConnection = function (socket) {
  var emptyAttempts = this.connectionAttemptsSent - this.connectionAttempsRecieved;
  if (emptyAttempts <= 2) {
    if (this.connectionAttemptsSent === 0) {
      showState("", false);
    }
    this.connectionAttemptsSent++;
    socket.send(JSON.stringify({
      check: {
        status: "heartbeat"
      }
    }));
  } else {
    this.connectionAttemptsSent = 0;
    this.connectionAttempsRecieved = 0;
    socket.dispatchEvent(new Event('close'))
  }
}

OodShell.prototype.sendString = function (str) {
  // Just like a keystroke, except str was generated by the
  // terminal itself.
  // Most likely you'll do the same this as onVTKeystroke.
  this.onVTKeystroke(str)
};

OodShell.prototype.onTerminalResize = function (columns, rows) {
  // React to size changes here.
  // Secure Shell pokes at NaCl, which eventually results in
  // some ioctls on the host.
  this.socket.send(JSON.stringify({
    resize: {
      cols: columns,
      rows: rows
    }
  }));
};

OodShell.prototype.onSessionEnd = function (code, reason) {
  this.socket.close(code, reason);
}

function showState(text, showBool) {
  var stateDiv = document.getElementById('state');
  var stateText = document.getElementById('state-text');

  stateText.textContent = text;
  if (showBool) {
    stateDiv.classList.remove('connected-state');
    stateDiv.classList.add('connecting-state');
  } else {
    stateDiv.classList.remove('connecting-state');
    stateDiv.classList.add('connected-state');
  }
}
