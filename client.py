"""
Python Chat Application  -  CLIENT SIDE
=======================================

Start server.py FIRST, then run:     python client.py

How it works
------------
* The client connects to the server using a TCP socket.
* After connecting, both sides can send messages to each other at any time
  (two-way communication).
* Networking runs in background threads so the window never freezes.
* Every message is sent as one line of UTF-8 text ending with a newline ("\\n").
"""

import queue
import select
import socket
import threading
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

# --------------------------------------------------------------------------
# Settings (must be the same in server.py)
# --------------------------------------------------------------------------
HOST = "127.0.0.1"   # address of the server (localhost = same computer)
PORT = 12345
ENCODING = "utf-8"
BUFFER_SIZE = 4096
CONNECT_TIMEOUT = 5  # seconds to wait for the server


# --------------------------------------------------------------------------
# Networking part (no GUI code here)
# --------------------------------------------------------------------------
class ChatClient:
    """Connects to the server, receives its messages and sends messages to it.

    The background threads never touch the GUI. They only put events into
    `self.events`, and the GUI reads them from there.

    Event types:  ("status", text)  ("system", text)  ("received", text)
                  ("connected", None)  ("disconnected", None)
                  ("connect_failed", None)
    """

    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sock = None
        self._connecting = False

    # ---- public API ------------------------------------------------------
    def is_connected(self):
        with self._lock:
            return self._sock is not None

    def connect(self):
        """Start connecting in the background. Safe to call again after a failure."""
        with self._lock:
            if self._sock is not None or self._connecting:
                return
            self._connecting = True
        self.events.put(("status", f"Connecting to {self.host}:{self.port} ..."))
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, text):
        """Send one message to the server.
        Returns True on success, False if not connected / sending failed."""
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return False
        with self._lock:
            sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall((text + "\n").encode(ENCODING))
            return True
        except OSError:
            return False

    def stop(self):
        self._stop.set()
        with self._lock:
            sock, self._sock = self._sock, None
        self._close(sock)

    # ---- internals -------------------------------------------------------
    @staticmethod
    def _close(sock):
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _run(self):
        # 1) connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((self.host, self.port))
            sock.settimeout(None)
        except OSError as exc:
            self._close(sock)
            with self._lock:
                self._connecting = False
            if not self._stop.is_set():
                if isinstance(exc, ConnectionRefusedError):
                    reason = "The server is not running. Start server.py first."
                elif isinstance(exc, socket.timeout):
                    reason = "The server did not answer in time."
                else:
                    reason = str(exc)
                self.events.put(("system", f"Could not connect: {reason}"))
                self.events.put(("status", "Not connected"))
                self.events.put(("connect_failed", None))
            return

        with self._lock:
            self._sock = sock
            self._connecting = False
        if self._stop.is_set():
            self.stop()
            return
        self.events.put(("status", f"Connected to {self.host}:{self.port}"))
        self.events.put(("system", "Connected to the server. You can chat now!"))
        self.events.put(("connected", None))

        # 2) receive until the connection ends
        self._receive_loop(sock)

        with self._lock:
            was_connected = self._sock is sock
            if was_connected:
                self._sock = None
        self._close(sock)
        if was_connected and not self._stop.is_set():
            self.events.put(("disconnected", None))
            self.events.put(("status", "Not connected"))
            self.events.put(("system", "Disconnected from the server."))

    def _receive_loop(self, sock):
        buffer = b""
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([sock], [], [], 0.5)
                if not ready:
                    continue
                data = sock.recv(BUFFER_SIZE)
            except (OSError, ValueError):
                break
            if not data:          # empty data = the other side closed the connection
                break
            buffer += data
            while b"\n" in buffer:   # TCP is a stream: split it into whole messages
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode(ENCODING, errors="replace").strip()
                if text:
                    self.events.put(("received", text))


# --------------------------------------------------------------------------
# Window (GUI) part
# --------------------------------------------------------------------------
class ClientWindow:
    ROLE = "Client"   # label for messages typed in this window
    PEER = "Server"   # label for messages that arrive from the other side

    def __init__(self, root):
        self.root = root
        self.net = ChatClient()
        self._closing = False

        root.title("Client")
        root.geometry("440x540+560+80")
        root.minsize(360, 400)

        # status line + (re)connect button
        top = tk.Frame(root)
        top.pack(fill="x", padx=8, pady=4)
        self.status_var = tk.StringVar(value="Starting ...")
        tk.Label(top, textvariable=self.status_var, anchor="w",
                 fg="#444444").pack(side="left", fill="x", expand=True)
        self.connect_btn = tk.Button(top, text="Connect", width=10, command=self.net.connect)
        self.connect_btn.pack(side="right")

        # chat history (read-only)
        self.chat = scrolledtext.ScrolledText(
            root, wrap="word", state="disabled", font=("Consolas", 10),
            bg="white", relief="solid", bd=1)
        self.chat.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.chat.tag_config("sent", foreground="#1a56db")
        self.chat.tag_config("received", foreground="#0e7a3b")
        self.chat.tag_config("system", foreground="#777777", font=("Consolas", 9, "italic"))

        # message box + Send button
        bottom = tk.Frame(root)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        self.entry = tk.Entry(bottom, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", self.send_message)
        self.send_btn = tk.Button(bottom, text="Send", width=10, command=self.send_message)
        self.send_btn.pack(side="left", padx=(6, 0))
        self.set_input_enabled(False)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_events)
        self.net.connect()   # connect automatically when the window opens

    # ---- helpers ---------------------------------------------------------
    def set_input_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.config(state=state)
        self.send_btn.config(state=state)
        # the Connect button is only useful while we are NOT connected
        self.connect_btn.config(state="disabled" if enabled else "normal")
        if enabled:
            self.entry.focus_set()

    def add_line(self, kind, text):
        """kind = 'sent' | 'received' | 'system'"""
        stamp = datetime.now().strftime("%H:%M:%S")
        if kind == "sent":
            line = f"[{stamp}] {self.ROLE}: {text}\n"
        elif kind == "received":
            line = f"[{stamp}] {self.PEER}: {text}\n"
        else:
            line = f"[{stamp}] * {text}\n"
        self.chat.config(state="normal")
        self.chat.insert("end", line, kind)
        self.chat.config(state="disabled")
        self.chat.see("end")

    # ---- actions ---------------------------------------------------------
    def send_message(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return "break"
        if self.net.send(text):
            self.add_line("sent", text)
            self.entry.delete(0, "end")
        else:
            self.add_line("system", "Message NOT sent - you are not connected.")
        return "break"

    def process_events(self):
        """Runs every 100 ms in the GUI thread and shows what the network thread reported."""
        try:
            while True:
                kind, payload = self.net.events.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind in ("system", "received"):
                    self.add_line(kind, payload)
                elif kind == "connected":
                    self.set_input_enabled(True)
                elif kind in ("disconnected", "connect_failed"):
                    self.set_input_enabled(False)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(100, self.process_events)

    def on_close(self):
        self._closing = True
        self.net.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    ClientWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
