"""Stage timing and atomic progress records."""
import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import psutil


class TelemetryError(RuntimeError):
    pass


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.writing')
    temporary.write_text(json.dumps(value, ensure_ascii=True, allow_nan=False), encoding='utf-8')
    # Retry transient Windows file locks.
    for attempt in range(12):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as error:
            if attempt == 11:
                raise TelemetryError('atomic output replacement remained locked: '+str(path)) from error
            time.sleep(min(.002 * (2**attempt), .05))


class Recorder:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.started = time.perf_counter()
        self.stack = []
        self.seconds = defaultdict(float)
        self.counts = defaultdict(int)
        self.work = defaultdict(int)
        self.latest = {}
        self.events = []
        self.stage_deadline = None
        self.stage_group = None
        self.process = psutil.Process()

    def publish(self, **values):
        self.latest.update(values)
        self.latest.update(phase=self.stack[-1] if self.stack else 'between_stages',
                           elapsed_seconds=time.perf_counter() - self.started,
                           rss_bytes=self.process.memory_info().rss,
                           group=self.stage_group, group_deadline_perf=self.stage_deadline)
        if self.path:
            atomic_json(self.path, self.latest)

    def group(self, name, seconds):
        self.stage_group = name
        self.stage_deadline = time.perf_counter() + seconds
        self.publish()

    @contextmanager
    def span(self, name):
        self.stack.append(name)
        start = time.perf_counter()
        self.publish(last_event='start')
        self.events.append({'phase': name, 'event': 'start', 'elapsed': start-self.started,
                            'rss': self.latest['rss_bytes']})
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.seconds[name] += elapsed
            self.counts[name] += 1
            self.events.append({'phase': name, 'event': 'end', 'elapsed': time.perf_counter()-self.started,
                                'rss': self.process.memory_info().rss})
            self.stack.pop()
            self.publish(last_event='end', last_completed=name)

    def result(self):
        return {'phase_seconds': dict(self.seconds), 'phase_calls': dict(self.counts),
                'operation_counts': dict(self.work), 'events': self.events,
                'note': 'Nested phase seconds overlap; use engine timing for additive primary accounting.'}
