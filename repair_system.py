from __future__ import annotations
from database import db, MOCK_OWNER_PASSWORD, MOCK_TECH_PASSWORD
import hashlib
import hmac
import logging
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional

from models import User, Customer, Technician, Owner, ComputerEquipment, ServiceTicket

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "repair_system.db"
LOG_PATH = APP_DIR / "repair_system.log"

PBKDF2_ITERATIONS = 240_000
IDLE_TIMEOUT_SECONDS = 10 * 60
REFRESH_INTERVAL_MS = 15_000

log = logging.getLogger("repair_system")


def setup_logging() -> None:
  handler = RotatingFileHandler(
      LOG_PATH, maxBytes=500_000, backupCount=3, encoding="utf-8"
  )
  handler.setFormatter(
      logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
  )
  log.setLevel(logging.INFO)
  if not log.handlers:
    log.addHandler(handler)


# ==========================================
# 0. ERRORS, VALIDATION & SECURITY HELPERS
# ==========================================
class AppError(Exception):
  """An error whose message is safe and useful to show to the user."""


class ValidationError(AppError):
  pass


class AuthError(AppError):
  pass


class NotFoundError(AppError):
  pass


TICKET_RE = re.compile(r"^TKT-(\d{1,9})$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PHONE_CHARS_RE = re.compile(r"^[0-9+\-() ]+$")


def clean_text(
    value: Optional[str],
    label: str,
    max_len: int,
    required: bool = True,
    allow_newlines: bool = False,
) -> str:
  value = (value or "").strip()
  if allow_newlines:
    value = "\n".join(line.rstrip() for line in value.splitlines())
  else:
    value = " ".join(value.split())
  if required and not value:
    raise ValidationError(f"{label} is required.")
  if len(value) > max_len:
    raise ValidationError(f"{label} must be at most {max_len} characters.")
  if any(ord(c) < 32 and c not in "\n" for c in value):
    raise ValidationError(f"{label} contains invalid characters.")
  return value


def clean_email(value: Optional[str], required: bool = False) -> str:
  value = clean_text(value, "Email address", 120, required=required)
  if value and not EMAIL_RE.match(value):
    raise ValidationError("Email address is not valid (e.g. name@example.com).")
  return value


def clean_phone(value: Optional[str]) -> str:
  value = clean_text(value, "Phone number", 25)
  digits = re.sub(r"\D", "", value)
  if not PHONE_CHARS_RE.match(value) or not 7 <= len(digits) <= 15:
    raise ValidationError(
        "Phone number must contain 7-15 digits (only digits, spaces, + - ( ))."
    )
  return value


def phone_digits(value: str) -> str:
  return re.sub(r"\D", "", value or "")


def validate_password(password: Optional[str]) -> str:
  if password is None or not 8 <= len(password) <= 128:
    raise ValidationError("Password must be 8-128 characters long.")
  if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
    raise ValidationError("Password must contain at least one letter and one number.")
  return password


def hash_password(password: str, salt: Optional[bytes] = None,
                  iterations: int = PBKDF2_ITERATIONS):
  salt = salt or secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
  return salt.hex(), digest.hex(), iterations


def verify_password(password: str, salt_hex: str, hash_hex: str, iterations: int) -> bool:
  _, candidate, _ = hash_password(password, bytes.fromhex(salt_hex), iterations)
  return hmac.compare_digest(candidate, hash_hex)


class RateLimiter:
  """Locks a key out for a while after too many failures."""

  def __init__(self, max_attempts: int = 5, lock_seconds: int = 60):
    self._max = max_attempts
    self._lock_seconds = lock_seconds
    self._failures: Dict[str, int] = {}
    self._locked_until: Dict[str, float] = {}

  def check(self, key: str) -> None:
    until = self._locked_until.get(key, 0.0)
    remaining = until - time.monotonic()
    if remaining > 0:
      raise AuthError(
          f"Too many failed attempts. Try again in {int(remaining) + 1} seconds."
      )
    if until:
      self._locked_until.pop(key, None)
      self._failures.pop(key, None)

  def fail(self, key: str) -> None:
    self._failures[key] = self._failures.get(key, 0) + 1
    if self._failures[key] >= self._max:
      self._locked_until[key] = time.monotonic() + self._lock_seconds

  def reset(self, key: str) -> None:
    self._failures.pop(key, None)
    self._locked_until.pop(key, None)


# ==========================================
# 1. SERVICE LAYER (SQLite persistence + rules)
# ==========================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL,
  phone_digits TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS technicians (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  specialization TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  technician_id INTEGER REFERENCES technicians(id),
  device_type TEXT NOT NULL DEFAULT 'Laptop',
  brand TEXT NOT NULL,
  model TEXT NOT NULL,
  serial TEXT NOT NULL DEFAULT '',
  issue TEXT NOT NULL,
  diagnosis TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('Pending','Diagnosing','In Repair','Ready for Pickup','Closed','Cancelled')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_tech ON tickets(technician_id);
CREATE TABLE IF NOT EXISTS credentials (
  key TEXT PRIMARY KEY,
  salt TEXT NOT NULL,
  hash TEXT NOT NULL,
  iterations INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT NOT NULL
);
"""


def now_iso() -> str:
  return datetime.now().isoformat(timespec="seconds")


class RepairService:
  """All business operations and SQLite persistence."""

  MAX_OPEN_TICKETS_PER_CUSTOMER = 10
  
  def _seed_initial_data(self):
    """Fully connects and seeds technicians, credentials, and mockup service tickets from database.py[cite: 1]."""
    cursor = self._conn.execute("SELECT COUNT(*) FROM technicians")
    if cursor.fetchone()[0] == 0:
      for t_id, tech in db.technicians.items():
        cursor_exec = self._conn.execute(
            "INSERT INTO technicians (name, email, specialization, active) VALUES (?, ?, ?, ?)",
            (tech.name, tech.email, tech.specialization, 1 if tech.is_active else 0)
        )
        tech_db_id = cursor_exec.lastrowid
        salt, digest, iters = hash_password(MOCK_TECH_PASSWORD)
        self._conn.execute(
            "INSERT OR REPLACE INTO credentials(key, salt, hash, iterations) VALUES (?,?,?,?)",
            (f"tech:{tech_db_id}", salt, digest, iters)
        )

    if not self.has_owner_password():
      self._store_credential("owner", MOCK_OWNER_PASSWORD)
      self._audit("system", "OWNER_PASSWORD_AUTO_SEEDED", "Default owner password seeded from database.py[cite: 1]")

    cursor = self._conn.execute("SELECT COUNT(*) FROM tickets")
    if cursor.fetchone()[0] == 0:
      tech_rows = self._conn.execute("SELECT id, name FROM technicians").fetchall()
      tech_name_to_id = {row["name"]: row["id"] for row in tech_rows}

      for t_key, ticket in db.tickets.items():
        cust = ticket.customer
        eq = ticket.equipment
        
        cust_row = self._conn.execute(
            "SELECT id FROM customers WHERE phone_digits=? AND lower(name)=lower(?)",
            (cust.phone_digits, cust.name)
        ).fetchone()
        if cust_row:
          cust_id = cust_row["id"]
        else:
          cust_id = self._conn.execute(
              "INSERT INTO customers(name, email, phone, phone_digits) VALUES (?,?,?,?)",
              (cust.name, cust.email, cust.phone_number, cust.phone_digits)
          ).lastrowid

        tech_db_id = None
        if ticket.assigned_technician:
          tech_db_id = tech_name_to_id.get(ticket.assigned_technician.name)

        stamp = now_iso()
        self._conn.execute(
            "INSERT INTO tickets(customer_id, technician_id, device_type, brand, model, serial, issue, diagnosis, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                cust_id,
                tech_db_id,
                eq.device_type,
                eq.brand,
                eq.model,
                eq.serial_number,
                ticket.issue,
                ticket.diagnosis,
                ticket.status,
                stamp,
                stamp
            )
        )
      self._audit("system", "MOCK_TICKETS_SEEDED", "Mockup service tickets seeded from database.py[cite: 1]")

  def __init__(self, db_path=DB_PATH, seed: bool = True):
    self.seeded = seed
    self._conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=10)
    self._conn.row_factory = sqlite3.Row
    self._conn.execute("PRAGMA foreign_keys = ON")
    self._conn.execute("PRAGMA busy_timeout = 5000")
    try:
      self._conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
      pass
      
    self._conn.executescript(SCHEMA)
    
    try:
      self._conn.execute("ALTER TABLE tickets ADD COLUMN device_type TEXT NOT NULL DEFAULT 'Laptop'")
    except sqlite3.OperationalError:
      pass

    if seed:
      self._seed_initial_data()

    self._login_limiter = RateLimiter(5, 60)
    self._lookup_limiter = RateLimiter(10, 60)

  def close(self) -> None:
    try:
      self._conn.close()
    except sqlite3.Error:
      pass

  @contextmanager
  def _tx(self):
    self._conn.execute("BEGIN IMMEDIATE")
    try:
      yield
    except BaseException:
      self._conn.execute("ROLLBACK")
      raise
    else:
      self._conn.execute("COMMIT")

  @staticmethod
  def _actor_label(actor) -> str:
    if isinstance(actor, User):
      return f"{actor.role}:{actor.user_id}:{actor.name}"
    return str(actor)

  def _audit(self, actor, action: str, detail: str = "") -> None:
    self._conn.execute(
        "INSERT INTO audit_log(ts, actor, action, detail) VALUES (?,?,?,?)",
        (now_iso(), self._actor_label(actor), action, detail),
    )

  def list_audit(self, actor: User, limit: int = 500) -> List[sqlite3.Row]:
    self._require_owner(actor)
    return self._conn.execute(
        "SELECT ts, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()

  def _store_credential(self, key: str, password: str) -> None:
    salt, digest, iters = hash_password(validate_password(password))
    self._conn.execute(
        "INSERT INTO credentials(key, salt, hash, iterations) VALUES (?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET salt=excluded.salt, hash=excluded.hash, "
        "iterations=excluded.iterations",
        (key, salt, digest, iters),
    )

  def _verify_credential(self, key: str, password: str) -> bool:
    row = self._conn.execute(
        "SELECT salt, hash, iterations FROM credentials WHERE key=?", (key,)
    ).fetchone()
    if row is None:
      hash_password(password or "", b"\x00" * 16)
      return False
    return verify_password(password or "", row["salt"], row["hash"], row["iterations"])

  def has_owner_password(self) -> bool:
    return self._conn.execute(
        "SELECT 1 FROM credentials WHERE key='owner'"
    ).fetchone() is not None

  def set_initial_owner_password(self, password: str) -> None:
    with self._tx():
      if self.has_owner_password():
        raise AuthError("An owner password has already been set.")
      self._store_credential("owner", password)
      self._audit("system", "OWNER_PASSWORD_SET", "Initial owner password created")

  @staticmethod
  def _make_owner() -> Owner:
    return Owner("owner", "Shop Owner", "", "Main Branch")

  def authenticate_owner(self, password: str) -> Owner:
    key = "login:owner"
    self._login_limiter.check(key)
    ok = self._verify_credential("owner", password)
    with self._tx():
      self._audit("owner", "LOGIN_OK" if ok else "LOGIN_FAILED", "")
    if not ok:
      self._login_limiter.fail(key)
      raise AuthError("Incorrect owner password. Access rejected.")
    self._login_limiter.reset(key)
    return self._make_owner()

  def authenticate_technician(self, tech_id: str, password: str) -> Technician:
    key = f"login:tech:{tech_id}"
    self._login_limiter.check(key)
    tech = self._technician_map().get(self._to_int(tech_id))
    ok = self._verify_credential(f"tech:{tech_id}", password)
    if tech is None or not tech.is_active:
      ok = False
    with self._tx():
      self._audit(f"technician:{tech_id}", "LOGIN_OK" if ok else "LOGIN_FAILED", "")
    if not ok:
      self._login_limiter.fail(key)
      raise AuthError("Incorrect password, or this account is not active.")
    self._login_limiter.reset(key)
    return tech

  def change_password(self, actor: User, old_password: str, new_password: str) -> None:
    if isinstance(actor, Owner):
      key = "owner"
    elif isinstance(actor, Technician):
      key = f"tech:{actor.user_id}"
    else:
      raise AuthError("Not allowed.")
    limiter_key = f"change:{key}"
    self._login_limiter.check(limiter_key)
    if not self._verify_credential(key, old_password):
      self._login_limiter.fail(limiter_key)
      raise AuthError("Current password is incorrect.")
    self._login_limiter.reset(limiter_key)
    with self._tx():
      self._verify_actor(actor)
      self._store_credential(key, new_password)
      self._audit(actor, "PASSWORD_CHANGED", "")

  @staticmethod
  def _to_int(value) -> int:
    try:
      return int(value)
    except (TypeError, ValueError):
      raise NotFoundError("Record not found.")

  @staticmethod
  def _require_owner(actor: User) -> None:
    if not isinstance(actor, Owner):
      raise AuthError("Only the owner can perform this action.")

  def _technician_map(self) -> Dict[int, Technician]:
    busy = {
        r[0] for r in self._conn.execute(
            "SELECT DISTINCT technician_id FROM tickets WHERE technician_id IS NOT NULL "
            "AND status IN ('Diagnosing','In Repair')"
        )
    }
    result = {}
    for r in self._conn.execute("SELECT * FROM technicians ORDER BY name"):
      result[r["id"]] = Technician(
          str(r["id"]), r["name"], r["email"], r["specialization"],
          is_active=bool(r["active"]), is_available=r["id"] not in busy,
      )
    return result

  def _verify_actor(self, actor: User) -> None:
    if isinstance(actor, Owner):
      return
    if isinstance(actor, Technician):
      current = self._technician_map().get(self._to_int(actor.user_id))
      if current is None or not current.is_active:
        raise AuthError("Your account is no longer active.")
      return
    raise AuthError("Not allowed.")

  _TICKET_SELECT = (
      "SELECT t.*, c.name AS c_name, c.email AS c_email, c.phone AS c_phone "
      "FROM tickets t JOIN customers c ON c.id = t.customer_id"
  )

  @staticmethod
  def _ticket_from_row(row, techs: Dict[int, Technician]) -> ServiceTicket:
    customer = Customer(str(row["customer_id"]), row["c_name"], row["c_email"], row["c_phone"])
    dtype = row["device_type"] if "device_type" in row.keys() else "Laptop"
    equipment = ComputerEquipment(str(row["id"]), row["brand"], row["model"], row["serial"], device_type=dtype)
    tech = techs.get(row["technician_id"]) if row["technician_id"] else None
    return ServiceTicket(
        row["id"], customer, equipment,
        service_type="Walk-In", pickup_details="N/A", comm_preference="Phone Call",
        initial_problem=row["issue"], diagnosis=row["diagnosis"],
        status=row["status"], technician=tech, pk=row["id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )

  def _load_ticket(self, pk) -> ServiceTicket:
    row = self._conn.execute(self._TICKET_SELECT + " WHERE t.id = ?",
                             (self._to_int(pk),)).fetchone()
    if row is None:
      raise NotFoundError("Ticket not found.")
    return self._ticket_from_row(row, self._technician_map())

  def _save_ticket(self, t: ServiceTicket) -> None:
    tech_id = int(t.assigned_technician.user_id) if t.assigned_technician else None
    self._conn.execute(
        "UPDATE tickets SET diagnosis=?, status=?, technician_id=?, updated_at=? WHERE id=?",
        (t.diagnosis, t.status, tech_id, now_iso(), t.pk),
    )

  def submit_ticket(self, name, email, phone, device_type, brand, model, serial, issue) -> str:
    name = clean_text(name, "Full name", 80)
    email = clean_email(email)
    phone = clean_phone(phone)
    device_type = clean_text(device_type, "Device type", 30)
    brand = clean_text(brand, "Brand", 40)
    model = clean_text(model, "Model", 60)
    serial = clean_text(serial, "Serial number", 60, required=False)
    issue = clean_text(issue, "Problem description", 1000, allow_newlines=True)
    digits = phone_digits(phone)
    with self._tx():
      row = self._conn.execute(
          "SELECT id FROM customers WHERE phone_digits=? AND lower(name)=lower(?)",
          (digits, name),
      ).fetchone()
      if row:
        cid = row["id"]
        if email:
          self._conn.execute("UPDATE customers SET email=? WHERE id=?", (email, cid))
      else:
        cid = self._conn.execute(
            "INSERT INTO customers(name, email, phone, phone_digits) VALUES (?,?,?,?)",
            (name, email, phone, digits),
        ).lastrowid
      open_rows = self._conn.execute(
          "SELECT brand, model, serial FROM tickets WHERE customer_id=? "
          "AND status NOT IN ('Closed','Cancelled')", (cid,),
      ).fetchall()
      if len(open_rows) >= self.MAX_OPEN_TICKETS_PER_CUSTOMER:
        raise AppError("Too many open tickets for this customer. Please wait for repairs to finish.")
      for r in open_rows:
        if (r["brand"].lower(), r["model"].lower(), r["serial"].lower()) == (
            brand.lower(), model.lower(), serial.lower()):
          raise AppError("An open ticket for this exact device already exists.")
      stamp = now_iso()
      
      pk = self._conn.execute(
          "INSERT INTO tickets(customer_id, device_type, brand, model, serial, issue, diagnosis, "
          "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
          (cid, device_type, brand, model, serial, issue, ServiceTicket.NO_DIAGNOSIS,
           "Pending", stamp, stamp),
      ).lastrowid
      
      code = f"TKT-{pk:05d}"
      self._audit("customer", "TICKET_CREATED", f"{code} for {name}")
    return code

  def lookup_ticket(self, code: str, phone: str) -> ServiceTicket:
    self._lookup_limiter.check("lookup")
    match = TICKET_RE.match((code or "").strip())
    ticket = None
    if match:
      try:
        ticket = self._load_ticket(int(match.group(1)))
      except NotFoundError:
        ticket = None
    supplied = phone_digits(phone)
    expected = ticket.customer.phone_digits if ticket else "x"
    if ticket is None or not supplied or not hmac.compare_digest(supplied, expected):
      self._lookup_limiter.fail("lookup")
      raise AppError("No ticket matches that Ticket ID and phone number.")
    self._lookup_limiter.reset("lookup")
    return ticket

  def list_tickets(self, actor: User, status: Optional[str] = None,
                   search: str = "") -> List[ServiceTicket]:
    self._verify_actor(actor)
    sql, params = self._TICKET_SELECT, []
    clauses = []
    if isinstance(actor, Technician):
      clauses.append("t.technician_id = ?")
      params.append(int(actor.user_id))
    if status and status != "All":
      clauses.append("t.status = ?")
      params.append(status)
    if clauses:
      sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY t.id DESC"
    techs = self._technician_map()
    tickets = [self._ticket_from_row(r, techs) for r in self._conn.execute(sql, params)]
    needle = (search or "").strip().lower()
    if needle:
      def hit(t: ServiceTicket) -> bool:
        hay = " ".join([
            t.ticket_id, t.customer.name, t.customer.phone_number,
            t.equipment.brand, t.equipment.model, t.equipment.serial_number,
        ]).lower()
        return needle in hay
      tickets = [t for t in tickets if hit(t)]
    return tickets

  def get_ticket(self, actor: User, pk) -> ServiceTicket:
    self._verify_actor(actor)
    ticket = self._load_ticket(pk)
    if isinstance(actor, Technician):
      tech = ticket.assigned_technician
      if tech is None or tech.user_id != actor.user_id:
        raise AuthError("You are not allowed to view this ticket.")
    return ticket

  def assign_technician(self, actor: User, ticket_pk, tech_id) -> ServiceTicket:
    self._require_owner(actor)
    with self._tx():
      ticket = self._load_ticket(ticket_pk)
      tech = self._technician_map().get(self._to_int(tech_id))
      if tech is None:
        raise NotFoundError("Technician not found.")
      ticket.assign_technician(tech, actor)
      self._save_ticket(ticket)
      self._audit(actor, "TICKET_ASSIGNED", f"{ticket.ticket_id} -> {tech.name}")
    return ticket

  def save_diagnosis(self, actor: User, ticket_pk, text: str) -> ServiceTicket:
    with self._tx():
      self._verify_actor(actor)
      ticket = self._load_ticket(ticket_pk)
      ticket.update_diagnosis(text, actor)
      self._save_ticket(ticket)
      self._audit(actor, "DIAGNOSIS_UPDATED", ticket.ticket_id)
    return ticket

  def change_status(self, actor: User, ticket_pk, new_status: str) -> ServiceTicket:
    with self._tx():
      self._verify_actor(actor)
      ticket = self._load_ticket(ticket_pk)
      old = ticket.status
      ticket.update_status(new_status, actor)
      self._save_ticket(ticket)
      self._audit(actor, "STATUS_CHANGED", f"{ticket.ticket_id}: {old} -> {new_status}")
    return ticket
  
  def list_login_technicians(self) -> List[Technician]:
    return [t for t in self._technician_map().values() if t.is_active]
    
  def list_technicians(self, actor: User, active_only: bool = False) -> List[Technician]:
    self._require_owner(actor)
    techs = list(self._technician_map().values())
    return [t for t in techs if t.is_active] if active_only else techs

  def add_technician(self, actor: User, name, email, specialization, password) -> Technician:
    self._require_owner(actor)
    name = clean_text(name, "Name", 80)
    email = clean_email(email)
    specialization = clean_text(specialization, "Specialization", 80)
    with self._tx():
      tid = self._conn.execute(
          "INSERT INTO technicians(name, email, specialization, active) VALUES (?,?,?,1)",
          (name, email, specialization),
      ).lastrowid
      self._store_credential(f"tech:{tid}", password)
      self._audit(actor, "TECHNICIAN_ADDED", f"{name} (id {tid})")
    return self._technician_map()[tid]

  def set_technician_active(self, actor: User, tech_id, active: bool) -> None:
    self._require_owner(actor)
    with self._tx():
      tech = self._technician_map().get(self._to_int(tech_id))
      if tech is None:
        raise NotFoundError("Technician not found.")
      if not active and tech.is_active and not tech.is_available:
        raise AppError(f"{tech.name} has an active repair. Reassign or finish it first.")
      self._conn.execute("UPDATE technicians SET active=? WHERE id=?",
                         (1 if active else 0, int(tech.user_id)))
      self._audit(actor, "TECHNICIAN_ACTIVATED" if active else "TECHNICIAN_DEACTIVATED", tech.name)

  def reset_technician_password(self, actor: User, tech_id, new_password: str) -> None:
    self._require_owner(actor)
    with self._tx():
      tech = self._technician_map().get(self._to_int(tech_id))
      if tech is None:
        raise NotFoundError("Technician not found.")
      self._store_credential(f"tech:{tech.user_id}", new_password)
      self._login_limiter.reset(f"login:tech:{tech.user_id}")
      self._audit(actor, "TECHNICIAN_PASSWORD_RESET", tech.name)

  def stats(self, actor: User) -> Dict[str, int]:
    self._require_owner(actor)
    counts = {s: 0 for s in ServiceTicket.VALID_STATUSES}
    for r in self._conn.execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"):
      counts[r["status"]] = r["n"]
    counts["Available technicians"] = sum(
        1 for t in self._technician_map().values() if t.is_available)
    return counts

  def backup_to(self, actor: User, path: str) -> None:
    self._require_owner(actor)
    dest = sqlite3.connect(path)
    try:
      self._conn.backup(dest)
    finally:
      dest.close()
    with self._tx():
      self._audit(actor, "BACKUP", Path(path).name)