"""Bounded process ownership and native X11/OCR driver; no GPUI test-platform substitutes."""
import ctypes
import ctypes.util
import io
import json
import os
import re
import selectors
import signal
import subprocess
import threading
import time
from pathlib import Path
from PIL import Image, ImageChops
from native_assertions import (GateFailure, UtilityTimeout, require, sha256, marker, window_ok,
                               capture_ok, clipboard_ok, reported_errors)

class Owner:
    def __init__(self, env, deadline, log_cap=2*1024*1024, canceled=lambda: False):
        self.env, self.deadline, self.log_cap = env, deadline, log_cap
        self.canceled = canceled
        self.processes, self.logs, self.commands = [], {}, []
        self.total_log_bytes = 0
        self.png_count = self.png_bytes = 0
        self.fatal = None
        self.lock = threading.Lock()
        self.threads = []
        self.killed_groups = set()

    def check(self):
        require(not self.canceled(), "Native gate interrupted")
        require(self.fatal is None, self.fatal or "Background failure")
        require(time.monotonic() < self.deadline, "Native stage deadline exceeded")
        for name, data in self.logs.items():
            if name.startswith("native-"):
                reported_errors(data.decode("utf-8", errors="replace"))

    def kill(self, process):
        if process.pid in self.killed_groups:
            return
        self.killed_groups.add(process.pid)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def start(self, name, args, env=None, stdin=False):
        self.check()
        require(name not in self.logs, "Duplicate process log name")
        process = subprocess.Popen(list(map(str, args)), env=env or self.env,
                                   stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        self.killed_groups.discard(process.pid)
        self.processes.append(process)
        self.logs[name] = bytearray()
        def drain():
            try:
                while True:
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    with self.lock:
                        if self.total_log_bytes + len(chunk) > self.log_cap:
                            self.fatal = "Complete background log cap exceeded"
                            self.kill(process)
                            break
                        self.logs[name].extend(chunk)
                        self.total_log_bytes += len(chunk)
            except Exception as exc:
                self.fatal = "Background log reader failed: " + str(exc)
            finally:
                process.stdout.close()
                self.kill(process)
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        self.threads.append(reader)
        self.check()
        return process

    def run(self, args, timeout=10, input_data=None, cap=1024*1024, check=True, env=None,
            record_output=False):
        self.check()
        require(len(self.commands) < 4096, "Utility command count cap exceeded")
        args = list(map(str, args))
        started = time.monotonic()
        limit = min(started + timeout, self.deadline)
        process = subprocess.Popen(args, env=env or self.env,
                                   stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        self.killed_groups.discard(process.pid)
        self.processes.append(process)
        writer_errors = []
        def write():
            try:
                process.stdin.write(input_data)
                process.stdin.close()
            except BrokenPipeError:
                pass
            except Exception as exc:
                writer_errors.append(str(exc))
        writer = None
        if input_data is not None:
            writer = threading.Thread(target=write, daemon=True)
            writer.start()
        output, errors = bytearray(), bytearray()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, output)
        selector.register(process.stderr, selectors.EVENT_READ, errors)
        safe_args = args[:-1] + ["<synthetic-cookie-redacted>"] if args[0] == "xauth" else args
        row = {"argv": safe_args, "pid": process.pid, "started_ns": time.monotonic_ns(), "status": "running"}
        self.commands.append(row)
        try:
            while selector.get_map():
                self.check()
                remaining = limit - time.monotonic()
                ready = selector.select(timeout=max(0, min(0.1, remaining)))
                if remaining <= 0 and (process.poll() is None or not ready):
                    raise UtilityTimeout("Utility deadline exceeded: " + args[0])
                # A finished leader may have ready EOF/data after the deadline.
                # Drain that readiness; an inherited orphan pipe still times out.
                for key, _ in ready:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    require(len(output) + len(errors) + len(chunk) <= cap,
                            "Utility output cap exceeded: " + args[0])
                    key.data.extend(chunk)
            try:
                process.wait(timeout=max(0.1, limit-time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise UtilityTimeout("Utility did not exit after closing pipes: " + args[0]) from exc
            if writer:
                writer.join(timeout=1)
                require(not writer.is_alive() and not writer_errors, "Utility input writer failed")
            row.update(status="success" if process.returncode == 0 else "nonzero",
                       exit_code=process.returncode, stdout_bytes=len(output),
                       stderr_bytes=len(errors), duration_ms=(time.monotonic()-started)*1000)
            require(not check or process.returncode == 0,
                    "Utility failed: " + args[0] + ": " + errors.decode(errors="replace")[-1000:])
            return bytes(output)
        except BaseException as exc:
            row.update(status="failure", failure_kind=type(exc).__name__, failure=str(exc),
                       returncode_before_cleanup=process.poll())
            self.kill(process)
            process.wait(timeout=3)
            raise
        finally:
            row.update(stdout_bytes=len(output), stderr_bytes=len(errors),
                       stdout_sha256=sha256(bytes(output)), stderr_sha256=sha256(bytes(errors)),
                       finished_ns=time.monotonic_ns(), duration_ms=(time.monotonic()-started)*1000)
            selector.close()
            # Clean immediately; do not retain exited PIDs or utility pipe FDs.
            self.kill(process)
            process.wait(timeout=3)
            if writer:
                writer.join(timeout=1)
                require(not writer.is_alive(), "Utility input writer survived cleanup")
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
            self.processes.remove(process)
            if record_output:
                with self.lock:
                    require(self.total_log_bytes + len(output) + len(errors) <= self.log_cap,
                            "Complete utility diagnostic log cap exceeded")
                    self.total_log_bytes += len(output) + len(errors)
                row["stdout"] = bytes(output).decode("utf-8", errors="replace")
                row["stderr"] = bytes(errors).decode("utf-8", errors="replace")

    def close(self):
        for process in reversed(self.processes):
            self.kill(process)
        for process in self.processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.fatal = "Process-group cleanup did not finish"
        for reader in self.threads:
            reader.join(timeout=3)
            if reader.is_alive():
                self.fatal = "Log reader survived process cleanup"
        for process in self.processes:
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()

class Driver:
    def __init__(self, owner, process, evidence, case, spec, fixture):
        self.owner, self.process, self.evidence, self.case, self.spec = owner, process, evidence, case, spec
        self.fixture = fixture
        self.window = None
        self.counter = 0
        self.saved_bytes = 0
        self.captures, self.inputs = [], []
        self.last_shot, self.failure_saved = None, False
        self.xlib = ctypes.CDLL(ctypes.util.find_library("X11"))
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.xlib.XInternAtom.restype = ctypes.c_ulong
        self.xlib.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.xlib.XGetSelectionOwner.restype = ctypes.c_ulong
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        previous_auth = os.environ.get("XAUTHORITY")
        try:
            os.environ["XAUTHORITY"] = owner.env["XAUTHORITY"]
            self.display = self.xlib.XOpenDisplay(owner.env["DISPLAY"].encode())
        finally:
            if previous_auth is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = previous_auth
        require(self.display, "Cannot open X11 display for selection ownership")
        self.clipboard_atom = self.xlib.XInternAtom(self.display, b"CLIPBOARD", 0)

    def close(self):
        self.xlib.XCloseDisplay(self.display)

    def alive(self):
        self.owner.check()
        require(self.process.poll() is None, "Native process exited before scenario completion")

    def wait_window(self):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            self.alive()
            output = self.owner.run(["xdotool", "search", "--onlyvisible", "--pid", self.process.pid],
                                    timeout=2, check=False).decode()
            ids = [int(word) for word in output.split() if word.isdigit()]
            require(len(ids) <= 1, "Multiple mapped windows for target PID")
            if ids:
                self.window = ids[0]
                meta = self.metadata()
                window_ok(meta, self.process.pid)
                self.owner.run(["xdotool", "windowactivate", "--sync", self.window])
                require(int(self.owner.run(["xdotool", "getactivewindow"]).strip()) == self.window,
                        "Target native window is not active")
                return meta
            time.sleep(0.1)
        raise GateFailure("No mapped native window within startup deadline")

    def metadata(self):
        self.alive()
        props = self.owner.run(["xprop", "-id", self.window, "_NET_WM_PID", "WM_CLASS", "_NET_WM_NAME"]).decode()
        stats = self.owner.run(["xwininfo", "-id", self.window, "-stats"]).decode()
        def number(pattern, text):
            found = re.search(pattern, text)
            require(found is not None, "Missing native window metadata: " + pattern)
            return int(found.group(1))
        result = {"id": self.window, "pid": number(r"_NET_WM_PID.*?=\s*(\d+)", props),
                  "wm_class": next((line for line in props.splitlines() if line.startswith("WM_CLASS")), ""),
                  "title": next((line for line in props.splitlines() if line.startswith("_NET_WM_NAME")), ""),
                  "viewable": "Map State: IsViewable" in stats,
                  "width": number(r"Width:\s*(\d+)", stats),
                  "height": number(r"Height:\s*(\d+)", stats),
                  "x": number(r"Absolute upper-left X:\s*(-?\d+)", stats),
                  "y": number(r"Absolute upper-left Y:\s*(-?\d+)", stats)}
        window_ok(result, self.process.pid)
        return result

    def capture(self, ocr=True):
        meta = self.metadata()
        data = self.owner.run(["import", "-window", self.window, "-depth", "8", "png:-"],
                              timeout=5, cap=5*1024*1024)
        at = time.monotonic_ns()
        image = Image.open(io.BytesIO(data)).convert("RGB")
        require(image.size == (meta["width"], meta["height"]), "Native capture size mismatch")
        words, raw = [], ""
        if ocr:
            buffer = io.BytesIO()
            image.resize((image.width*2, image.height*2)).save(buffer, format="PNG")
            raw = self.owner.run(["tesseract", "stdin", "stdout", "-l", "eng+rus", "--psm", "11", "tsv"],
                                 input_data=buffer.getvalue(), timeout=10, cap=1024*1024).decode()
            for line in raw.splitlines()[1:]:
                fields = line.split("\t", 11)
                if len(fields) == 12 and fields[11].strip():
                    words.append({"text": fields[11].strip(), "left": int(fields[6])/2,
                                  "top": int(fields[7])/2, "width": int(fields[8])/2,
                                  "height": int(fields[9])/2, "confidence": float(fields[10])})
        receipt = {"captured_ns": at, "window_id": self.window,
                   "size": list(image.size), "png_sha256": sha256(data),
                   "window": meta, "words": words, "ocr_tsv": raw,
                   "input_seq": len(self.inputs),
                   "protocol_trace_seq_at_capture": len(self.fixture.trace),
                   "enqueued_runtime_seq_at_capture": self.fixture.seq}
        self.last_shot = {"receipt": receipt, "data": data, "image": image}
        return self.last_shot

    def save(self, shot, stage):
        reserve = not stage.endswith("-failure")
        require(self.owner.png_count < self.spec["max_png_count"] - int(reserve), "PNG count cap exceeded")
        maximum = self.spec["max_png_bytes"] - (5*1024*1024 if reserve else 0)
        require(self.owner.png_bytes + len(shot["data"]) <= maximum,
                "PNG byte cap exceeded")
        self.counter += 1
        self.owner.png_count += 1
        self.owner.png_bytes += len(shot["data"])
        name = f"{self.case}-{self.counter:02d}-{stage}.png"
        require(re.fullmatch(r"[a-zA-Z0-9_-]+\.png", name), "Unsafe evidence filename")
        (self.evidence / name).write_bytes(shot["data"])
        self.saved_bytes += len(shot["data"])
        receipt = {**shot["receipt"], "file": name, "stage": stage}
        self.captures.append(receipt)
        return receipt

    def save_failure(self, stage):
        if self.failure_saved or self.last_shot is None:
            return
        self.failure_saved = True
        try:
            self.save(self.last_shot, stage + "-failure")
        except Exception as exc:
            # Retention failure never turns a semantic failure into PASS or hides it.
            self.owner.fatal = self.owner.fatal or "Failure screenshot retention failed: " + str(exc)

    def wait_markers(self, names, since, stage, timeout=None, predicate=None):
        until = time.monotonic() + (timeout or self.spec["stage_seconds"])
        last = None
        while time.monotonic() < until:
            self.alive()
            last = self.capture()
            capture_ok(last["receipt"], since, last["receipt"]["window"])
            last["receipt"]["stage_since_ns"] = since
            last["receipt"]["required_visible_markers"] = list(names)
            counts = [sum(word["text"].casefold() == name.casefold()
                          and word["confidence"] >= 65 for word in last["receipt"]["words"])
                      for name in names]
            require(all(count <= 1 for count in counts), "Duplicate semantic screen marker")
            if not all(counts):
                time.sleep(0.1)
                continue
            points = [marker(last["receipt"]["words"], name) for name in names]
            if predicate is not None:
                predicate(points, last)
            self.save(last, stage)
            return last
        if last:
            self.save_failure(stage)
        raise GateFailure("No unambiguous semantic screen acknowledgement: " + stage)

    def input(self, args, label):
        self.alive()
        require(int(self.owner.run(["xdotool", "getactivewindow"]).strip()) == self.window,
                "Refusing XTEST input to an unfocused window")
        stamp = time.monotonic_ns()
        self.owner.run(["xdotool", *args], timeout=4)
        self.inputs.append({"seq": len(self.inputs)+1, "at_ns": stamp, "action": label, "argv": args})
        return stamp

    def move(self, x, y):
        return self.input(["mousemove", "--window", str(self.window), str(round(x)), str(round(y))], "pointer")

    def click(self, x, y, label):
        self.move(x, y)
        return self.input(["click", "1"], label)

    def type_composer(self, text, replace=False):
        meta = self.metadata()
        self.click(meta["width"]*0.60, meta["height"]-80, "focus composer")
        if replace:
            self.input(["key", "--clearmodifiers", "ctrl+a"], "select retained draft")
        stamp = self.input(["type", "--clearmodifiers", "--delay", "3", text], "type synthetic composer text")
        return self.wait_markers([text], stamp, "composer")

    def send_composer(self):
        return self.input(["key", "--clearmodifiers", "Return"], "submit composer")

    def wheel(self, down=True, count=3):
        meta = self.metadata()
        self.move(meta["width"]*0.65, meta["height"]*0.45)
        return self.input(["click", "--repeat", str(count), "--delay", "50", "5" if down else "4"],
                          "wheel down" if down else "wheel up")

    def selection_owner(self):
        return int(self.xlib.XGetSelectionOwner(self.display, self.clipboard_atom))

    def clipboard(self):
        return self.owner.run(["xclip", "-selection", "clipboard", "-out", "-target", "UTF8_STRING"],
                              timeout=2, cap=65536).decode("utf-8")

    def copy_delta_row(self, fixture, expected, shot, nonce):
        first = marker(shot["receipt"]["words"], "BEGINMARK")
        last = marker(shot["receipt"]["words"], "ENDMARK")
        tool = marker(shot["receipt"]["words"], "barrierprobe")
        bounds = (max(0, int(first["left"])-3), int(last["top"]+last["height"])+2,
                  int(first["left"])+25, int(tool["top"])-2)
        require(bounds[3]-bounds[1] >= 12, "No localized assistant action strip")
        self.move(20, 10)
        # A timed settle is not an acknowledgement; stable pixels below validate it.
        until = time.monotonic() + 5
        before = None
        while time.monotonic() < until:
            a = self.capture(ocr=False)
            time.sleep(0.15)
            b = self.capture(ocr=False)
            if ImageChops.difference(a["image"].crop(bounds), b["image"].crop(bounds)).getbbox() is None:
                before = b
                break
        require(before is not None, "Assistant action strip did not settle")
        self.move(first["left"]+5, first["top"]+3)
        time.sleep(0.15)
        hover = self.capture(ocr=False)
        diff = ImageChops.difference(before["image"].crop(bounds), hover["image"].crop(bounds))
        bbox = diff.point(lambda p: 255 if p > 24 else 0).getbbox()
        require(bbox is not None, "Hover did not reveal native assistant Copy")
        x = bounds[0] + (bbox[0]+bbox[2])/2
        y = bounds[1] + (bbox[1]+bbox[3])/2
        self.move(x, y)
        shown = self.wait_markers(["BEGINMARK", "ENDMARK", "barrierprobe", "Копировать"],
                                  time.monotonic_ns(), "native-copy-target")
        icon = (round(x)-8, round(y)-8, round(x)+8, round(y)+8)
        icon_before = sha256(shown["image"].crop(icon).tobytes())
        sentinel = self.owner.start("clipboard-sentinel-" + self.case, ["xclip", "-selection", "clipboard",
                                    "-in", "-quiet"], stdin=True)
        sentinel.stdin.write(nonce.encode())
        sentinel.stdin.close()
        until = time.monotonic() + 3
        old_owner, installed = 0, None
        while time.monotonic() < until:
            old_owner = self.selection_owner()
            if old_owner:
                try:
                    installed = self.clipboard()
                except GateFailure:
                    installed = None
                if installed == nonce:
                    break
            time.sleep(0.05)
        require(installed == nonce, "Cannot install external CLIPBOARD sentinel")
        before_ns = time.monotonic_ns()
        click_ns = self.click(x, y, "native assistant Copy")
        until = time.monotonic() + 1.5
        actual = None
        while time.monotonic() < until:
            actual = self.clipboard()
            if actual == expected and self.selection_owner() != old_owner:
                break
            time.sleep(0.05)
        after_ns = time.monotonic_ns()
        changed = self.capture(ocr=False)
        self.save(changed, "native-copy-feedback")
        receipt = {"selection": "CLIPBOARD", "nonce": nonce, "before": installed,
                   "after": actual, "owner_before": old_owner, "owner_after": self.selection_owner(),
                   "before_ns": before_ns, "click_ns": click_ns, "after_ns": after_ns,
                   "icon_before_sha256": icon_before,
                   "icon_after_sha256": sha256(changed["image"].crop(icon).tobytes()),
                   "icon_crop": list(icon), "target_visible": True,
                   "icon_claim": "Localized control pixels changed after native click; not icon classification",
                   "owner_identity_limit": "GPUI owns CLIPBOARD through a separate helper XID without _NET_WM_PID",
                   "target_capture": shown["receipt"]["png_sha256"]}
        clipboard_ok(receipt, expected, fixture.trace)
        fixture.oracle_closed = True
        return receipt

    def red_stop_candidates(self, image):
        # Only the source-defined small danger control at the composer's lower right.
        pixels = image.load()
        points = set()
        for y in range(max(0, image.height-120), image.height-15):
            for x in range(int(image.width*0.65), image.width-15):
                r, g, b = pixels[x,y]
                if r > 105 and r-g > 35 and r-b > 15:
                    points.add((x,y))
        groups = []
        while points:
            todo = [points.pop()]
            group = []
            while todo:
                point = todo.pop()
                group.append(point)
                x, y = point
                for near in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if near in points:
                        points.remove(near)
                        todo.append(near)
            if len(group) >= 40:
                xs, ys = zip(*group)
                box = (min(xs), min(ys), max(xs)+1, max(ys)+1)
                if 12 <= box[2]-box[0] <= 60 and 12 <= box[3]-box[1] <= 60:
                    groups.append(box)
        return groups

    def stop_control(self, stage):
        until = time.monotonic() + self.spec["stage_seconds"]
        groups = []
        while time.monotonic() < until:
            shot = self.capture()
            groups = self.red_stop_candidates(shot["image"])
            require(len(groups) <= 1, "Ambiguous native Stop controls")
            if groups:
                break
            time.sleep(0.1)
        require(len(groups) == 1, "Cannot uniquely localize native Stop control")
        box = groups[0]
        x,y = (box[0]+box[2])/2, (box[1]+box[3])/2
        self.move(x,y)
        self.wait_markers(["Остановить"], time.monotonic_ns(), stage)
        return x,y
