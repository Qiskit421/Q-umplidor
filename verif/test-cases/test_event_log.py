import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src")) 
import event_log as ev  # noqa: E402


class TestEventLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.log = ev.EventLog(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_records_events_in_order(self):
        self.log.record(ev.JOB_SUBMITTED, job_id=1, cmd="sleep 5")
        self.log.record(ev.JOB_STARTED, job_id=1, pid=123)
        events = self.log.read()
        self.assertEqual([e["event"] for e in events], [ev.JOB_SUBMITTED, ev.JOB_STARTED])
        self.assertEqual([e["seq"] for e in events], [1, 2])

    def test_filter_by_job(self):
        self.log.record(ev.JOB_SUBMITTED, job_id=1)
        self.log.record(ev.JOB_SUBMITTED, job_id=2)
        self.assertEqual(len(self.log.read(job_id=2)), 1)

    def test_persists_and_continues_sequence(self):
        self.log.record(ev.SYSTEM_STARTED)
        again = ev.EventLog(self.path)
        self.assertEqual(again.record(ev.SYSTEM_STOPPED)["seq"], 2)

    def test_ignores_corrupt_line(self):
        self.log.record(ev.JOB_SUBMITTED, job_id=1)
        with self.path.open("a") as f:
            f.write('{"seq": 2, "event": "JOB_STA')  # escritura cortada
        self.assertEqual(len(self.log.read()), 1)

    def test_thread_safety(self):
        def work(i):
            for _ in range(50):
                self.log.record(ev.JOB_SUBMITTED, job_id=i)
        threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        seqs = [e["seq"] for e in self.log.read()]
        self.assertEqual(sorted(seqs), list(range(1, 201)))

    def test_access_denied_se_registra_con_ip_y_motivo(self): #RF-20 Y RF-23
        self.log.record(ev.ACCESS_DENIED, ip="10.0.0.5", motivo="IP_NO_PERMITIDA")
        eventos = self.log.read()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["event"], ev.ACCESS_DENIED)
        texto = ev.format_entry(eventos[0])
        self.assertIn("ip=10.0.0.5", texto)
        self.assertIn("motivo=IP_NO_PERMITIDA", texto)

    def test_access_denied_no_se_mezcla_con_eventos_de_trabajos(self):
        self.log.record(ev.JOB_SUBMITTED, job_id=1)
        self.log.record(ev.ACCESS_DENIED, ip="10.0.0.5", motivo="MAX_CLIENTES")
        self.assertEqual([e["event"] for e in self.log.read(job_id=1)], [ev.JOB_SUBMITTED])
        self.assertEqual([e["event"] for e in self.log.read()], [ev.JOB_SUBMITTED, ev.ACCESS_DENIED])

    def test_access_denied_persiste_tras_reiniciar(self): #RF-14
        self.log.record(ev.ACCESS_DENIED, ip="10.0.0.5", motivo="IP_NO_PERMITIDA")
        again = ev.EventLog(self.path)
        eventos = again.read()
        self.assertEqual([e["event"] for e in eventos], [ev.ACCESS_DENIED])

if __name__ == "__main__":
    unittest.main()