from models import ComputerEquipment, Customer, Owner, ServiceTicket, Technician

# Demo passwords referenced by the GUI on startup
MOCK_OWNER_PASSWORD = "OwnerPassword123!"
MOCK_TECH_PASSWORD = "TechPassword123!"


class SharedDatabase:
  """Centralized storage for tickets, equipment, and system users with pre-populated mockup data."""

  def __init__(self):
    self.tickets = {}

    # Pre-registered Technicians (Expanded with more specialists)
    self.technicians = {
        "T001": Technician(
            "T001",
            "Engr. Santos",
            "santos@shop.com",
            "Motherboard & Microsoldering",
        ),
        "T002": Technician(
            "T002", "Engr. Reyes", "reyes@shop.com", "Software & OS Recovery"
        ),
        "T003": Technician(
            "T003",
            "Engr. Dela Cruz",
            "delacruz@shop.com",
            "Hardware Assembly & Thermal Servicing",
        ),
        "T004": Technician(
            "T004",
            "Engr. Bautista",
            "bautista@shop.com",
            "Desktop Custom Rigs & GPU Diagnostics",
        ),
        "T005": Technician(
            "T005",
            "Engr. Mendoza",
            "mendoza@shop.com",
            "Laptop Screen & Keyboard Hardware Repairs",
        ),
    }

    # Store Owner / Admin
    self.owner = Owner(
        "O001", "Director Marcus", "marcus@shop.com", "Main Branch"
    )

    # Populate Mockup Service Tickets
    self._init_mockup_tickets()

  def _init_mockup_tickets(self):
    # Mockup Ticket 1: Laptop, Walk-In, Phone Call preference
    c1 = Customer(
        "C_TKT-101", "Juan Dela Cruz", "juan.dc@gmail.com", "09171234567"
    )
    eq1 = ComputerEquipment("EQ-501", "ASUS", "TUF Gaming F15", "SN-ASUS99281", device_type="Laptop")
    t1 = ServiceTicket(
        "TKT-101",
        c1,
        eq1,
        service_type="Walk-In",
        pickup_details="N/A (Walk-In)",
        comm_preference="Phone Call",
        initial_problem=(
            "Laptop suddenly shuts down during heavy gaming or rendering."
        ),
    )
    t1.assign_technician(self.technicians["T001"])
    t1.update_diagnosis(
        "Found dried up thermal paste and clogged cooling fans. Heatsink requires repasting."
    )
    t1.update_status("In Repair")
    t1.add_message(
        "Customer (Juan Dela Cruz)",
        "Please let me know if replacing the fans is necessary.",
    )
    t1.add_message(
        "Technician (Staff)",
        "We tested the fans; cleaning and repasting should suffice without replacement.",
    )
    self.tickets["TKT-101"] = t1

    # Mockup Ticket 2: Laptop, Shop Pickup, In-Person Discussion preference
    c2 = Customer(
        "C_TKT-102", "Maria Santos", "maria.santos@yahoo.com", "09189876543"
    )
    eq2 = ComputerEquipment("EQ-502", "Lenovo", "IdeaPad Slim 3", "SN-LEN77362", device_type="Laptop")
    t2 = ServiceTicket(
        "TKT-102",
        c2,
        eq2,
        service_type="Shop Pickup",
        pickup_details=(
            "Block 4 Lot 12, Malolos, Bulacan (Pickup on Oct 16, 2:00 PM)"
        ),
        comm_preference="In-Person Discussion",
        initial_problem=(
            "Blue screen of death (BSOD) appearing randomly upon booting Windows 11."
        ),
    )
    t2.assign_technician(self.technicians["T002"])
    t2.update_diagnosis(
        "Corrupted system files due to faulty Windows Update sector. Operating system reinstallation required."
    )
    t2.update_status("Ready for Pickup")
    t2.add_message(
        "Customer (Maria Santos)",
        "Can you backup my Documents folder before reinstalling?",
    )
    t2.add_message(
        "Technician (Staff)",
        "Yes, we successfully backed up your personal files to our secure local server.",
    )
    self.tickets["TKT-102"] = t2

    # Mockup Ticket 3: Desktop PC, Walk-In, Phone Call preference (Pending)
    c3 = Customer(
        "C_TKT-103", "Carlos Ramos", "carlos.ramos@gmail.com", "09195551234"
    )
    eq3 = ComputerEquipment("EQ-503", "Custom", "Desktop Gaming Rig (Ryzen 5 / RTX 3060)", "SN-PC110293", device_type="Desktop PC")
    t3 = ServiceTicket(
        "TKT-103",
        c3,
        eq3,
        service_type="Walk-In",
        pickup_details="N/A (Walk-In)",
        comm_preference="Phone Call",
        initial_problem="PC powers on with lights and fans, but no display output to monitor.",
    )
    # Assigning to our new Desktop specialist technician (T004)
    t3.assign_technician(self.technicians["T004"])
    t3.update_status("Diagnosing")
    self.tickets["TKT-103"] = t3


db = SharedDatabase()