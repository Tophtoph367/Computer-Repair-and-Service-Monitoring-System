"""
models.py - Core domain models using Object-Oriented Programming principles
=========================================================================
"""

from abc import ABC, abstractmethod
import re
from typing import List, Dict, Optional, Tuple


class User(ABC):
  """Abstract base class representing any system user[cite: 3]."""

  ROLE = "user"

  def __init__(self, user_id: str, name: str, email: str):
    self._user_id = user_id
    self._name = name
    self._email = email

  @property
  def user_id(self) -> str:
    return self._user_id

  @property
  def name(self) -> str:
    return self._name

  @property
  def email(self) -> str:
    return self._email

  @property
  def role(self) -> str:
    return self.ROLE

  @abstractmethod
  def get_role_description(self) -> str:
    pass


class Customer(User):
  """Represents a client requesting computer repair services[cite: 3]."""

  ROLE = "customer"

  def __init__(self, user_id: str, name: str, email: str, phone_number: str):
    super().__init__(user_id, name, email)
    self.__phone_number = phone_number

  @property
  def phone_number(self) -> str:
    return self.__phone_number

  @property
  def phone_digits(self) -> str:
    return re.sub(r"\D", "", self.__phone_number)

  def get_role_description(self) -> str:
    return f"Customer: {self._name} | Phone: {self.__phone_number}"


class Technician(User):
  """Represents technical staff handling repairs and diagnoses[cite: 3]."""

  ROLE = "technician"

  def __init__(self, user_id: str, name: str, email: str, specialization: str,
               is_active: bool = True, is_available: bool = True):
    super().__init__(user_id, name, email)
    self.__specialization = specialization
    self.__is_active = is_active
    self.__is_available = is_available

  @property
  def specialization(self) -> str:
    return self.__specialization

  @property
  def is_active(self) -> bool:
    return self.__is_active

  @property
  def is_available(self) -> bool:
    return self.__is_active and self.__is_available

  @is_available.setter
  def is_available(self, value: bool):
    self.__is_available = value

  def get_role_description(self) -> str:
    if not self.__is_active:
      status = "Deactivated"
    else:
      status = "Available" if self.__is_available else "Busy"
    return f"Technician: {self._name} [{self.__specialization}] - {status}"


class Owner(User):
  """Represents the shop administrator / owner[cite: 3]."""

  ROLE = "owner"

  def __init__(self, user_id: str, name: str, email: str, store_branch: str):
    super().__init__(user_id, name, email)
    self.__store_branch = store_branch

  @property
  def store_branch(self) -> str:
    return self.__store_branch

  def get_role_description(self) -> str:
    return f"Owner / Admin: {self._name} (Branch: {self.__store_branch})"


class ComputerEquipment:
  """Stores hardware specifications for devices brought in for repair[cite: 3]."""

  def __init__(self, equipment_id: str, brand: str, model: str, serial_number: str, device_type: str = "Laptop"):
    self.__equipment_id = equipment_id
    self.__brand = brand
    self.__model = model
    self.__serial_number = serial_number
    self.__device_type = device_type

  @property
  def equipment_id(self) -> str:
    return self.__equipment_id

  @property
  def brand(self) -> str:
    return self.__brand

  @property
  def model(self) -> str:
    return self.__model

  @property
  def serial_number(self) -> str:
    return self.__serial_number

  @property
  def device_type(self) -> str:
    return self.__device_type

  def get_equipment_info(self) -> str:
    sn = f" (SN: {self.__serial_number})" if self.__serial_number else ""
    dt = f"[{self.__device_type}] " if self.__device_type else ""
    return f"{dt}{self.__brand} {self.__model}{sn}"


class ServiceTicket:
  """
  Composes Customer, ComputerEquipment, and Technician[cite: 3].
  Manages repair stages, service modes, communication preferences, and chat history.
  """

  VALID_STATUSES = [
      "Pending", "Diagnosing", "In Repair", "Ready for Pickup", "Closed", "Cancelled"
  ]
  ACTIVE_STATUSES = ("Diagnosing", "In Repair")
  TERMINAL_STATUSES = ("Closed", "Cancelled")
  OWNER_ONLY_STATUSES = {"Closed", "Cancelled"}
  NO_DIAGNOSIS = "Not yet diagnosed"
  TRANSITIONS = {
      "Pending": {"Cancelled"},
      "Diagnosing": {"In Repair", "Ready for Pickup", "Cancelled"},
      "In Repair": {"Diagnosing", "Ready for Pickup", "Cancelled"},
      "Ready for Pickup": {"In Repair", "Closed"},
      "Closed": set(),
      "Cancelled": set(),
  }

  def __init__(self, ticket_id_or_pk, customer: Customer, equipment: ComputerEquipment,
               service_type: str = "Walk-In", pickup_details: str = "N/A",
               comm_preference: str = "Phone Call", initial_problem: str = "",
               diagnosis: Optional[str] = None, status: str = "Pending",
               technician: Optional[Technician] = None, pk: Optional[int] = None,
               created_at: str = "", updated_at: str = ""):
    if isinstance(ticket_id_or_pk, int) or (ticket_id_or_pk is not None and str(ticket_id_or_pk).isdigit()):
      self.__pk = int(ticket_id_or_pk)
      self.__custom_ticket_id = None
    else:
      self.__custom_ticket_id = ticket_id_or_pk
      self.__pk = pk

    if status not in self.VALID_STATUSES:
      status = "Pending"

    self.__customer = customer
    self.__equipment = equipment
    self.__service_type = service_type
    self.__pickup_details = pickup_details
    self.__comm_preference = comm_preference
    self.__issue = initial_problem or ""
    self.__diagnosis = diagnosis or self.NO_DIAGNOSIS
    self.__status = status
    self.__technician = technician
    self.__chat_history: List[Tuple[str, str]] = []
    self.__created_at = created_at
    self.__updated_at = updated_at

  @property
  def pk(self) -> Optional[int]:
    return self.__pk

  @property
  def ticket_id(self) -> str:
    if self.__custom_ticket_id:
      return self.__custom_ticket_id
    return f"TKT-{self.__pk:05d}" if self.__pk is not None else "(unsaved)"

  @property
  def customer(self) -> Customer:
    return self.__customer

  @property
  def equipment(self) -> ComputerEquipment:
    return self.__equipment

  @property
  def service_type(self) -> str:
    return self.__service_type

  @property
  def pickup_details(self) -> str:
    return self.__pickup_details

  @property
  def comm_preference(self) -> str:
    return self.__comm_preference

  @property
  def issue(self) -> str:
    return self.__issue

  @property
  def diagnosis(self) -> str:
    return self.__diagnosis

  @property
  def status(self) -> str:
    return self.__status

  @property
  def assigned_technician(self) -> Optional[Technician]:
    return self.__technician

  @property
  def created_at(self) -> str:
    return self.__created_at

  @property
  def updated_at(self) -> str:
    return self.__updated_at

  def _require_can_edit(self, actor: User) -> None:
    if actor.role == "owner":
      return
    if (actor.role == "technician" and self.__technician is not None
        and self.__technician.user_id == actor.user_id):
      return
    from repair_system import AuthError
    raise AuthError("You are not allowed to modify this ticket.")

  def allowed_next_statuses(self, actor: User) -> List[str]:
    try:
      self._require_can_edit(actor)
    except Exception:
      return []
    nxt = set(self.TRANSITIONS.get(self.__status, set()))
    if actor.role != "owner":
      nxt -= self.OWNER_ONLY_STATUSES
    return [s for s in self.VALID_STATUSES if s in nxt]

  def assign_technician(self, technician: Technician, actor: Optional[User] = None) -> None:
    if actor is not None and actor.role != "owner":
      from repair_system import AuthError
      raise AuthError("Only the owner can assign technicians.")
    if self.__status in self.TERMINAL_STATUSES or self.__status == "Ready for Pickup":
      from repair_system import AppError
      raise AppError(f"Cannot assign a technician to a ticket that is '{self.__status}'.")
    if not technician.is_active:
      from repair_system import AppError
      raise AppError(f"{technician.name} is deactivated and cannot take new work.")
    if self.__technician and self.__technician.user_id == technician.user_id:
      from repair_system import AppError
      raise AppError(f"{technician.name} is already assigned to this ticket.")
    if not technician.is_available:
      from repair_system import AppError
      raise AppError(f"Technician {technician.name} is currently assigned to another repair.")
    self.__technician = technician
    if self.__status == "Pending":
      self.__status = "Diagnosing"

  def update_diagnosis(self, diagnosis_text: str, actor: Optional[User] = None) -> None:
    if actor is not None:
      self._require_can_edit(actor)
    if self.__status in self.TERMINAL_STATUSES:
      from repair_system import AppError
      raise AppError(f"Ticket is {self.__status}; diagnosis can no longer be changed.")
    self.__diagnosis = diagnosis_text.strip()

  def update_status(self, new_status: str, actor: Optional[User] = None) -> None:
    if actor is not None:
      self._require_can_edit(actor)
    if new_status not in self.VALID_STATUSES:
      from repair_system import ValidationError
      raise ValidationError(f"Invalid status selection: '{new_status}'")
    if actor is not None and new_status not in self.allowed_next_statuses(actor):
      from repair_system import AppError
      raise AppError(f"You cannot move a ticket from '{self.__status}' to '{new_status}'.")
    if new_status == "Ready for Pickup" and self.__diagnosis == self.NO_DIAGNOSIS:
      from repair_system import AppError
      raise AppError("Record diagnosis notes before marking a ticket Ready for Pickup.")
    self.__status = new_status

  def add_message(self, sender: str, message: str) -> None:
    self.__chat_history.append((sender, message.strip()))

  def get_chat_transcript(self) -> str:
    if not self.__chat_history:
      return "No chat messages yet."
    return "\n".join(f"[{sender}]: {msg}" for sender, msg in self.__chat_history)

  def get_ticket_summary(self, for_customer: bool = False) -> str:
    tech_name = self.__technician.name if self.__technician else "Unassigned"
    created = self.__created_at.replace("T", " ") if self.__created_at else "N/A"
    updated = self.__updated_at.replace("T", " ") if self.__updated_at else "N/A"
    
    lines = [
        "-" * 50,
        f"TICKET ID     : {self.ticket_id}",
        f"STATUS        : {self.__status}",
        f"SERVICE TYPE  : {self.__service_type} ({self.__pickup_details})",
        f"COMM. PREF.   : {self.__comm_preference}",
        f"OPENED        : {created}",
        f"UPDATED       : {updated}",
        f"CUSTOMER      : {self.__customer.name} [{self.__customer.phone_number}]",
    ]
    if not for_customer and self.__customer.email:
      lines.append(f"EMAIL         : {self.__customer.email}")
    lines += [
        f"DEVICE        : {self.__equipment.get_equipment_info()}",
        f"TECHNICIAN    : {tech_name}",
        f"PROBLEM       : {self.__issue}",
        f"DIAGNOSIS     : {self.__diagnosis}",
    ]
    if self.__chat_history:
      lines.append(f"CHAT LOG      :\n{self.get_chat_transcript()}")
    lines.append("-" * 50)
    return "\n".join(lines)