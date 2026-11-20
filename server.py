"""
Python Chat Application  -  SERVER SIDE
=======================================

Run this file FIRST:      python server.py
Then run the client:      python client.py   (in a second terminal)

How it works
------------
* The server opens a TCP socket and listens for an incoming connection.
* Once a client connects, both sides can send messages to each other at any
  time (two-way communication).
* Networking runs in a background thread so the window never freezes.
* Every message is sent as one line of UTF-8 text ending with a newline ("\\n").
"""

import os
import queue
import select
import socket
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext

# --------------------------------------------------------------------------
# Settings (must be the same in client.py)
# --------------------------------------------------------------------------
HOST = "127.0.0.1"   # localhost -> client and server on the same computer
PORT = 12345         # change it if this port is already used on your PC
ENCODING = "utf-8"
BUFFER_SIZE = 4096


# --------------------------------------------------------------------------
# Networking part (no GUI code here)
# --------------------------------------------------------------------------
class ChatServer:
    """Listens for a client, receives its messages and sends messages back.

    The background thread never touches the GUI. It only puts events into
    `self.events`, and the GUI reads them from there.

    Event types:  ("status", text)  ("system", text)  ("received", text)
                  ("connected", None)  ("disconnected", None)  ("fatal", text)
    """

    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._server_sock = None
        self._conn = None
        self._thread = None

    # ---- public API ------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_connected(self):
        with self._lock:
            return self._conn is not None

    def send(self, text):
        """Send one message to the connected client.
        Returns True on success, False if nobody is connected / sending failed."""
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return False
        with self._lock:
            conn = self._conn
        if conn is None:
            return False
        try:
            conn.sendall((text + "\n").encode(ENCODING))
            return True
        except OSError:
            return False

    def stop(self):
        self._stop.set()
        with self._lock:
            conn, self._conn = self._conn, None
            server_sock, self._server_sock = self._server_sock, None
        self._close(conn)
        self._close(server_sock)

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
        # 1) create the listening socket
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if os.name != "nt":
                # On Linux/macOS this avoids "Address already in use" after a restart.
                # (Not used on Windows, where it would allow two servers on one port.)
                server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.host, self.port))
            server_sock.listen(1)
        except OSError as exc:
            self.events.put((
                "fatal",
                f"Could not start the server on {self.host}:{self.port}.\n\n"
                f"{exc}\n\nIs another server.py already running? "
                f"Close it, or change PORT in both files."))
            return

        with self._lock:
            self._server_sock = server_sock
        self.events.put(("status", f"Listening on {self.host}:{self.port} ..."))
        self.events.put(("system", "Server started. Waiting for a client to connect..."))

        # 2) accept clients one after another
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([server_sock], [], [], 0.5)
                if not ready:
                    continue
                conn, addr = server_sock.accept()
            except (OSError, ValueError):
                break  # server socket was closed -> shutting down

            with self._lock:
                self._conn = conn
            self.events.put(("status", f"Connected to {addr[0]}:{addr[1]}"))
            self.events.put(("system", f"Client connected from {addr[0]}:{addr[1]}"))
            self.events.put(("connected", None))

            self._receive_loop(conn)

            with self._lock:
                self._conn = None
            self._close(conn)
            if self._stop.is_set():
                break
            self.events.put(("disconnected", None))
            self.events.put(("status", "Client left. Waiting for a new client ..."))
            self.events.put(("system", "Client disconnected. Waiting for a new client..."))

    def _receive_loop(self, conn):
        buffer = b""
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([conn], [], [], 0.5)
                if not ready:
                    continue
                data = conn.recv(BUFFER_SIZE)
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
class ServerWindow:
    ROLE = "Server"   # label for messages typed in this window
    PEER = "Client"   # label for messages that arrive from the other side

    def __init__(self, root):
        self.root = root
        self.net = ChatServer()
        self._closing = False

        root.title("Server")
        root.geometry("440x540+80+80")
        root.minsize(360, 400)

        # status line
        self.status_var = tk.StringVar(value="Starting ...")
        tk.Label(root, textvariable=self.status_var, anchor="w",
                 fg="#444444", padx=8, pady=4).pack(fill="x")

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
        self.net.start()
        self.root.after(100, self.process_events)

    # ---- helpers ---------------------------------------------------------
    def set_input_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.config(state=state)
        self.send_btn.config(state=state)
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
            self.add_line("system", "Message NOT sent - no client is connected.")
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
                elif kind == "disconnected":
                    self.set_input_enabled(False)
                elif kind == "fatal":
                    self.status_var.set("Server could not start")
                    messagebox.showerror("Server error", payload)
                    self.on_close()
                    return
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
    ServerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
