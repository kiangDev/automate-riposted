import csv
import os
import re
import time
import traceback

from pywinauto import findwindows
from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto.timings import TimeoutError as PywinautoTimeoutError


CSV_FILENAME = "data.csv"
LOG_FILENAME = "success_log.txt"
CONTROLS_FILENAME = "controls.txt"
# แก้: ไฟล์ output แยกต่างหาก (ไม่แก้ data.csv ต้นฉบับ) มีคอลัมน์ TrackingNo
# เติมเลขพัสดุที่จับได้กลับเข้าไปทุกครั้งที่ทำรายการสำเร็จ เปิดด้วย Excel ได้
OUTPUT_CSV_FILENAME = "data_with_tracking.csv"


# ค่า default ใช้เมื่อ CSV ไม่มีคอลัมน์ หรือช่องนั้นว่าง
DEFAULT_PHONE_NUMBER = "0987654321"
DEFAULT_WEIGHT = "500"
# แก้: เปลี่ยนเป็น " " (เว้นวรรค) ให้ตรงกับตัวแรกสุดใน
# ADDRESS_SEARCH_FALLBACK_CANDIDATES ของจริง -- เมื่อก่อนตั้งเป็น "11" ทำให้
# " " ที่เพิ่งเพิ่มเข้าไปในลิสต์ fallback ไม่เคยถูกลองเป็นอันดับแรกจริงๆ เลย
# (เพราะ primary_search_term ต่อไว้หน้าสุดเสมอใน search_and_select_address)
DEFAULT_ADDRESS_SEARCH = "1"
# แก้: เช็คแล้วพบว่า data.csv มีรหัสไปรษณีย์ต่างกันมากกว่า 75 รหัส (ไม่ได้
# ซ้ำกันหมดแบบที่ทดสอบตอนแรก) เลขที่ "88"/"11" ฯลฯ เจาะจงกับซอยประชาอุทิศ 88
# (เขต 10140) เท่านั้น รหัสไปรษณีย์อื่นแทบไม่มีทางแมตช์เลย -- เพิ่ม " "
# (เว้นวรรค 1 ตัว) เป็นตัวแรกสุดที่ลอง เผื่อระบบคืนที่อยู่ทั้งหมดของรหัส
# ไปรษณีย์นั้นแบบไม่กรอง (ไม่ต้องพึ่งเดาเลขที่) ถ้าใช้ไม่ได้จริงค่อยไล่ตัวเลข
# ต่อเหมือนเดิม
ADDRESS_SEARCH_FALLBACK_CANDIDATES = ["1","11", "12", "88", "1", "2", "10"]

# ---------------------------------------------------------------
# แก้: TODO เดิมตรงนี้ไม่เคยถูกทำจริง -- ยืนยันจาก controls dump จริงแล้วว่า
# แอปไม่มีหน้า/ข้อความ "สำเร็จ" แบบนี้เลย wait_for_success() เลิกใช้ regex
# นี้แล้ว เปลี่ยนไปเช็ค MAIN_MENU_AUTO_ID แทน (ดูคอมเมนต์ตรงนั้น) เก็บตัวแปร
# นี้ไว้เฉยๆ ไม่ได้ใช้แล้ว กันเผื่อมีโค้ดอื่นอ้างถึง
# ---------------------------------------------------------------
SUCCESS_TITLE_RE = r".*(สำเร็จ|เสร็จสิ้น|พิมพ์เสร็จ).*"
# แก้: มีหลักฐานจริงแล้วว่าค่านี้ต่ำเกินไปอันตราย (เคยลอง 4 วิ แล้วเจอ
# "ไม่พบสัญญาณความสำเร็จ" ทั้งที่พิมพ์จริงน่าจะเสร็จแล้ว พอถือว่าไม่สำเร็จ
# recover_ui() ก็กดปุ่มหน้าหลักไม่ติดตามไปด้วย จนรายการถัดไปค้างสนิทต้อง
# kill โปรแกรมเอง) นี่คือค่าที่อันตรายที่สุดในไฟล์นี้ (ตัดสินว่ารายการนี้
# "สำเร็จจริง" ก่อนบันทึก log ถ้ารอไม่พอจะถือว่าไม่สำเร็จทั้งที่ปริ้นออกมา
# แล้วจริง แล้วพิมพ์ซ้ำอีกใบตอนรันใหม่) ตกลงกับผู้ใช้แล้วว่าใช้ 10 ไม่ควรลด
# ต่ำกว่านี้เพื่อความเร็ว เพราะเป็น "เพดาน" ไม่ใช่เวลารอตายตัว ใบที่พิมพ์เร็ว
# ปกติจะคืนค่าทันทีอยู่แล้วไม่ว่าตั้งเพดานไว้เท่าไหร่
SUCCESS_WAIT_TIMEOUT = 10

# เลขพัสดุ (tracking number) ของไปรษณีย์ไทย รูปแบบมาตรฐาน: ตัวอักษร 2 ตัว +
# ตัวเลข 9 หลัก + ตัวอักษร 2 ตัว (เช่น JH000205755TH) แมตช์ด้วย pattern นี้
# แทนการหา label ภาษาไทย (มักเพี้ยนผ่าน UI Automation เหมือนจุดอื่นๆ)
TRACKING_NUMBER_RE = re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$")

# ปุ่ม/เมนู "จุดเริ่มต้น" (รับฝากสิ่งของ) ที่ใช้ยืนยันว่ากลับมาหน้าแรกได้จริง
# หมายเหตุ: แอป Riposte ส่งค่า title ภาษาไทยออกมาทาง UI Automation แบบเพี้ยน
# (mojibake) ทำให้ค้นหาด้วย title_re ภาษาไทยไม่ได้ผล -> ใช้ auto_id แทน
HOME_AUTO_ID = "Shipping"
HOME_CONTROL_TYPE = "ListItem"

# แก้: auto_id ของหน้าเมนูหลักสุด (pane "Main" ตอนยังไม่ได้กด "รับฝากสิ่งของ")
# ยืนยันจาก controls dump จริงแล้วว่าหลังพิมพ์ใบปะหน้าสำเร็จ แอปจะกลับมาที่
# หน้านี้ทันที (ไม่มีหน้า/ข้อความ "สำเร็จ" ใดๆ เลย) ใช้เป็นสัญญาณยืนยันความ
# สำเร็จตัวจริงใน wait_for_success() แทนการเดา SUCCESS_TITLE_RE เดิม
MAIN_MENU_AUTO_ID = "Menu.MainMenu"

# ปุ่มเลือกกล่องสำเร็จรูป "ข" ที่หน้า MailPieceShape
# ยืนยันแล้วจาก controls dump จริง (dump.txt): tile "กล่องสำเร็จรูป ข" คือ
# hotkey เลข 4 บนหน้าจอ ซึ่งตรงกับ auto_id="MailPieceShape_9"
# (ค่าเดิม "MailPieceShape_ModelId-303" ไม่มีอยู่จริงในแอป เป็นค่าที่เดาไว้
# แล้วไม่เคยตรวจสอบ)
BOX_TYPE_AUTO_ID = "MailPieceShape_9"

# ปุ่ม "ถัดไป"/"ยืนยัน" (ปุ่มหลักของแต่ละหน้า, hotkey ENTER) และ
# ปุ่ม "ย้อนกลับ" (hotkey ESC) -- สังเกตจาก controls dump ว่าใช้ auto_id
# เดียวกันซ้ำทุกหน้าจอ (LocalCommand_*) ต่างกันแค่ label ข้อความ
# หมายเหตุ: ยังไม่ได้ยืนยัน 100% ว่าทุกหน้าใช้ auto_id นี้เหมือนกันหมด
# ถ้าเจอหน้าไหนกดไม่ติด ให้ตรวจสอบ auto_id จริงของหน้านั้นอีกที
SUBMIT_AUTO_ID = "LocalCommand_Submit"
PREVIOUS_AUTO_ID = "LocalCommand_Previous"
HOME_BUTTON_AUTO_ID = "LocalCommand_Home"

# หน้าคำถาม "สินค้าอันตราย" (EG.Shipping.DangerousGoodsQuestion) ที่แทรกมา
# หลังเลือกกล่องเสร็จ ยืนยันจาก controls dump แล้วว่ามีปุ่มตอบ 2 ปุ่ม:
# auto_id="Declined" กับ auto_id="Confirmed"
# ความหมายจริง (ยืนยันกับผู้ใช้แล้ว): "Confirmed" = ยืนยันว่า "ไม่มี"
# สินค้าอันตราย ใช้ปุ่มนี้เป็นค่า default สำหรับพัสดุทั่วไป
DANGEROUS_GOODS_ANSWER_AUTO_ID = "Confirmed"

# หน้าเลือกบริการ (EG.Shipping.Services) มีบริการ ~39 ตัวเรียงเลื่อนซ้าย-ขวา
# แต่ละตัวเป็นปุ่ม auto_id="ShippingService_<รหัส>" ไม่มีข้อความ/hotkey กำกับ
# เลยดูจาก dump ไม่ออกว่าตัวไหนคือบริการที่ต้องการ -- ผู้ใช้ยืนยันแล้วว่า
# "ShippingService_2572" (ตัวแรกสุด ซึ่งตอน dump ก็เห็นรายละเอียดราคา/
# ค่าธรรมเนียมโชว์อยู่แล้ว น่าจะถูกเลือกเป็น default อยู่ก่อนแล้วด้วย)
# คือตัวที่ต้องการใช้จริง
SHIPPING_SERVICE_AUTO_ID = "ShippingService_2572"

# แก้: Alert ถาม "ทำรายการซ้ำโดยใช้ข้อมูลกล่อง/สินค้าอันตราย/บริการเดิม
# ไหม" (auto_id="EG.Shipping.ConfirmNexModeAlert") ขึ้นทุกครั้งที่กด Home
# (auto_id=HOME_AUTO_ID) หลังเพิ่งทำรายการก่อนหน้าสำเร็จในเซสชันเดียวกัน
# (ยืนยันจากผู้ใช้ทดสอบมือแล้ว) มีปุ่ม auto_id="Yes" (ENTER) กับ
# auto_id="No" (ESC) -- ตอบ "Yes" เสมอ เพราะกล่อง/สินค้าอันตราย/บริการที่
# สคริปต์นี้ใช้เป็นค่าคงที่เดิมทุกแถวอยู่แล้ว (ไม่เคยเปลี่ยนตาม CSV) จึงไม่มี
# กรณีที่ต้องตอบ "No" เพื่อเริ่มใหม่ทั้งหมด ตอบ "Yes" แล้วจะข้ามหน้าสินค้า
# อันตรายไปเลย และบริการ 2572 จะถูกเลือกอัตโนมัติ (ยืนยันจากผู้ใช้แล้ว)
# ส่วนช่องที่ต้องเปลี่ยนทุกแถว (ชื่อ/รหัสไปรษณีย์/ที่อยู่) fill_edit() ใช้
# set_edit_text() ซึ่งเขียนทับค่าเดิมอยู่แล้ว (ไม่ได้ต่อท้าย) จึงปลอดภัย
REPEAT_TRANSACTION_ALERT_YES_AUTO_ID = "Yes"


def load_processed_data(log_filename=LOG_FILENAME):
    """อ่านรายการที่ทำสำเร็จแล้วจากไฟล์ log"""
    processed = set()

    if not os.path.exists(log_filename):
        return processed

    with open(log_filename, "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            # แก้: log แต่ละบรรทัดตอนนี้เป็น "identifier|เลขพัสดุ" (เผื่อบันทึก
            # เลขพัสดุด้วย) เอาแค่ส่วนก่อน "|" มาเช็คว่าทำไปแล้วหรือยัง
            # (รองรับ log เก่าที่ไม่มี "|" ด้วย เพราะ split("|", 1)[0] จะได้
            # ทั้งบรรทัดเหมือนเดิมถ้าไม่มี "|")
            identifier = line.split("|", 1)[0]
            processed.add(identifier)

    return processed


def clean_value(value):
    """แปลงค่า CSV เป็นข้อความและตัดช่องว่าง"""
    if value is None:
        return ""
    return str(value).strip()


def value_or_default(value, default):
    """
    แก้: ฟังก์ชันนี้เคยหายไปจากไฟล์อีกรอบ (โดนลบพร้อมกับ auditทั่ว) ทั้งที่
    ยังถูกเรียกใช้ทุกแถวใน main() (address_search/phone_number/weight) --
    ถ้าไม่มีฟังก์ชันนี้ สคริปต์จะ crash ทันทีตั้งแต่แถวแรก ก่อนแตะ UI ด้วยซ้ำ
    คืนค่าจาก CSV ถ้ามี ไม่งั้นใช้ค่า default
    """
    cleaned = clean_value(value)
    return cleaned if cleaned else default


def dump_controls_on_failure(window, tag):
    """
    แก้: ฟังก์ชันนี้เคยหายไปจากไฟล์เช่นกัน ทั้งที่ยังถูกเรียกใน
    wait_and_click() และ wait_for_success() ตอน error -- ถ้าไม่มีฟังก์ชันนี้
    ตอนหา control ไม่เจอครั้งแรก จะ crash ด้วย NameError แทนที่จะ dump ไฟล์
    ให้ดู debug ตามที่ควรจะเป็น เมื่อหา control ไม่เจอ ให้ dump control tree
    ปัจจุบันลงไฟล์แยก เพื่อเทียบกับ title_re/regex ที่ใช้ค้นหา ช่วย debug
    ได้เร็วขึ้น
    """
    filename = f"controls_fail_{tag}.txt"
    try:
        window.print_control_identifiers(filename=filename)
        print(f"[DEBUG] บันทึก control tree ตอน fail ลง {filename} แล้ว "
              f"-> เปิดไฟล์นี้เทียบกับ title_re ที่ใช้ค้นหา")
    except Exception as dump_error:
        print(f"[WARNING] dump control tree ไม่สำเร็จ: {dump_error}")



def wait_and_click(window, timeout=5, wait_states="exists visible enabled", **criteria):
    print(f"[DEBUG] กำลังค้นหา control: {criteria}")
    try:
        control = window.child_window(**criteria)
        control.wait(wait_states, timeout=timeout)
        wrapper = control.wrapper_object()

        print("[DEBUG] พบ control")
        print(f"        title        = {wrapper.window_text()!r}")
        print(f"        control_type = {wrapper.element_info.control_type!r}")
        print(f"        automation_id= {wrapper.element_info.automation_id!r}")

        wrapper.click_input()
        return wrapper

    except Exception as error:
        print(f"[ERROR] หา/คลิก control ไม่สำเร็จ: {criteria}")
        print(f"[ERROR] {type(error).__name__}: {error}")
        tag = criteria.get("title_re") or criteria.get("title") or criteria.get("auto_id") or "unknown"
        safe_tag = "".join(ch for ch in str(tag) if ch.isalnum())[:30] or "unknown"
        dump_controls_on_failure(window, safe_tag)
        raise


def resolve_edit_wrapper(wrapper, timeout=1.5):
    """
    ยืนยันจาก controls dump หน้ากรอกน้ำหนัก (EG.Shipping.Weight) แล้วว่า
    title_re ที่ใช้ค้นก่อนหน้านี้ (เช่น r".*น้ำหนัก.*") จะไปแมตช์กับ Static
    label (auto_id="LabelForTextBox" หรือ "Title"/"MainText") ซึ่งเป็นแค่
    ป้ายข้อความ ไม่ใช่ช่องกรอกจริง -- ช่องกรอกจริงเป็น control_type="Edit"
    แยกต่างหาก (เช่น auto_id="EG_WEIGHT_INPUT_ELEMENT") ที่อยู่ใน parent
    เดียวกันกับ label นั้น (auto_id ลงท้าย "..._UserControlBase")

    เลยต้องเช็คว่า control ที่หาเจอเป็น Edit จริงไหม ถ้าไม่ใช่ ให้ไต่ขึ้นไปหา
    parent แล้วหา Edit ที่อยู่ข้างเคียงแทน (ใช้ได้กับทุกหน้าที่ใช้ template
    เดียวกันนี้ โดยไม่ต้องรู้ auto_id เฉพาะของแต่ละหน้า)
    """
    if wrapper.element_info.control_type == "Edit":
        return wrapper

    print(
        f"[DEBUG] control ที่เจอไม่ใช่ Edit (เป็น {wrapper.element_info.control_type!r}, "
        f"auto_id={wrapper.element_info.automation_id!r}) -> ลองหา Edit ข้างเคียงแทน"
    )
    parent_wrapper = wrapper.parent()
    for child in parent_wrapper.children():
        if child.element_info.control_type == "Edit":
            print(
                f"[DEBUG] เจอ Edit ข้างเคียง auto_id={child.element_info.automation_id!r}"
            )
            return child

    raise RuntimeError(
        "หา Edit ข้างเคียงไม่เจอ (control ที่แมตช์ title_re/criteria เป็น "
        f"{wrapper.element_info.control_type!r} และไม่มี Edit อยู่ใน parent เดียวกัน)"
    )


def fill_edit(window, value, timeout=5, force_type_keys=False, **criteria):
    """
    รอช่องกรอก ล้างข้อมูลเดิม แล้วกรอกค่าใหม่

    force_type_keys=True: ข้าม set_edit_text() ไปเลย บังคับใช้ type_keys()
    (จำลองการพิมพ์จริง) เสมอ -- ใช้กับช่องที่มีพฤติกรรม "ค้นหาขณะพิมพ์"
    (search-as-you-type) เพราะ set_edit_text() ตั้งค่าผ่าน UI Automation
    ValuePattern ตรงๆ ซึ่งบางแอปไม่ trigger event ค้นหา (เหมือนจำลอง
    keyboard event ไม่ครบ) ทำให้ค่าโชว์ในช่องถูกต้อง แต่แอปไม่รู้ว่ามีการพิมพ์
    เกิดขึ้นจริง เลยไม่ค้นหาอะไรให้เลย
    """
    print(f"[DEBUG] กำลังค้นหาช่องกรอก: {criteria}")

    try:
        control = window.child_window(**criteria)
        control.wait("exists visible", timeout=timeout)

        raw_wrapper = control.wrapper_object()
        # แก้: เผื่อ criteria ที่ส่งมาไปแมตช์ label แทนที่จะเป็น Edit จริง
        wrapper = resolve_edit_wrapper(raw_wrapper, timeout=timeout)
        wrapper.click_input()

        print("[DEBUG] พบช่องกรอก")
        print(f"        control_type = {wrapper.element_info.control_type!r}")
        print(f"        automation_id= {wrapper.element_info.automation_id!r}")
        print(f"        title (ก่อนกรอก) = {wrapper.window_text()!r}")

        if force_type_keys:
            wrapper.type_keys("^a{BACKSPACE}")
            wrapper.type_keys(
                str(value),
                with_spaces=True,
                set_foreground=True,
            )
        else:
            try:
                wrapper.set_edit_text(str(value))

            except Exception:
                # แก้: ส่ง key ไปที่ wrapper โดยตรง ไม่ใช้ global send_keys
                # เพื่อป้องกันพิมพ์ผิดหน้าต่างถ้า focus หลุด
                wrapper.type_keys("^a{BACKSPACE}")
                wrapper.type_keys(
                    str(value),
                    with_spaces=True,
                    set_foreground=True,
                )

        # แก้: print ค่าจริงหลังกรอกเสร็จ (ของเดิม print ก่อนกรอก ทำให้ log
        # โชว์ค่าของรอบก่อนหน้า สับสนตอนดู debug log ย้อนหลัง)
        print(f"        title (หลังกรอก)  = {wrapper.window_text()!r}")

        return wrapper

    except Exception as error:
        print(f"[ERROR] กรอกข้อมูลไม่สำเร็จ: {criteria}")
        print(f"[ERROR] ค่าที่ต้องการกรอก: {value!r}")
        print(f"[ERROR] {type(error).__name__}: {error}")
        raise


def handle_repeat_transaction_alert(window, timeout=5):
    """
    หลังกด Home (auto_id=HOME_AUTO_ID) ถ้าเพิ่งทำรายการก่อนหน้าสำเร็จ แอปจะ
    ถาม Alert "ทำรายการซ้ำโดยใช้ข้อมูลเดิมไหม"
    (auto_id="EG.Shipping.ConfirmNexModeAlert") ตอบ "Yes" เสมอ (ดูเหตุผล
    เต็มที่คอมเมนต์ข้าง REPEAT_TRANSACTION_ALERT_YES_AUTO_ID ด้านบน) --
    ข้ามหน้าสินค้าอันตรายไปเลย และบริการ 2572 ถูกเลือกอัตโนมัติ ประหยัดเวลา
    ต่อใบได้เยอะ ยืนยันจากการทดสอบจริงของผู้ใช้แล้วว่า Yes=ทำซ้ำ (ไปหน้า
    เลือกกล่องเลย) No=กลับหน้าแรกเฉยๆ (ต้องกด "รับฝากสิ่งของ" ใหม่)

    timeout=5 เพราะทดสอบจริงพบว่า Alert นี้เด้งช้ากว่าที่คิด เช็คด้วย 2 วิ
    ไม่ทัน ทำให้โค้ดคิดว่าไม่มี Alert แล้วเดินหน้าต่อ แต่ Alert มาโผล่ทีหลัง
    ชนกับปุ่มอื่นแทน รอ 5 วิตรงนี้ให้ดักได้ทันตั้งแต่ต้น

    ถ้าไม่เจอ Alert (เช่น รายการแรกสุดของรัน ยังไม่มีรายการก่อนหน้าให้ทำซ้ำ)
    ข้ามไปเงียบๆ ไม่ throw
    """
    if is_control_visible(
        window,
        timeout=timeout,
        auto_id=REPEAT_TRANSACTION_ALERT_YES_AUTO_ID,
        control_type="Button",
    ):
        print("[DEBUG] พบ Alert ยืนยันทำรายการซ้ำ -> ตอบ 'Yes' (ใช้ข้อมูลเดิม)")
        wait_and_click(
            window,
            auto_id=REPEAT_TRANSACTION_ALERT_YES_AUTO_ID,
            control_type="Button",
        )


def handle_dangerous_goods_question(window, timeout=5):
    """
    หน้าคำถามสินค้าอันตราย (EG.Shipping.DangerousGoodsQuestion) จะแทรกโผล่มา
    หลังเลือกกล่องเสร็จ ไม่ได้โผล่ทุกครั้งแน่นอน (ยังไม่ยืนยัน) เลยเช็คก่อนว่า
    เจอปุ่ม "Confirmed" ไหม ถ้าไม่เจอภายใน timeout สั้นๆ ก็ข้ามไปเงียบๆ ไม่ throw
    """
    if is_control_visible(
        window, timeout=timeout, auto_id=DANGEROUS_GOODS_ANSWER_AUTO_ID, control_type="Button"
    ):
        print("[DEBUG] พบหน้าคำถามสินค้าอันตราย -> กด 'Confirmed' (ยืนยันว่าไม่มีสินค้าอันตราย)")
        wait_and_click(window, auto_id=DANGEROUS_GOODS_ANSWER_AUTO_ID, control_type="Button")
          # แก้: ลดจาก 1 วิ (ลด latency)
        click_next(window)


def handle_postcode_overlap_alert(window, timeout=5):
    """
    หลังกรอกรหัสไปรษณีย์ที่หน้า "Destination" (EG.Shipping.Destination,
    ช่อง auto_id="PostCodeDestination") บางครั้งรหัสที่พิมพ์ครอบคลุมหลาย
    พื้นที่ จะมี Alert แทรกขึ้นมา

    แก้: ยืนยันจาก controls dump จริงของ Alert นี้แล้ว 100% (ผู้ใช้ส่งมาตอน
    Alert กำลังโชว์อยู่จริง) นี่คือ Alert คนละตัวกับ
    EG.CustomerCapture.PostalCodeAlert (ดู
    handle_customer_capture_postal_code_alert ด้านล่าง) -- ตัวนี้คือ
    title="Alert", auto_id="THP.Shipping.PostcodeOverlap.AlertView" มี 2 ปุ่ม:
    - auto_id="ChangeCommand" ("เปลี่ยน", hotkey ESC)
    - auto_id="ProceedCommand" ("ดำเนินการ", hotkey ENTER)
      = ไปต่อโดยไม่ต้องเลือกพื้นที่เจาะจง (ค่าที่ใช้งานได้จริงมาตลอด)

    ก่อนหน้านี้เคยเข้าใจผิดคิดว่า auto_id="ProceedCommand" ไม่มีอยู่จริง
    (ไปเจอ dump ของ Alert อีกตัวที่หน้าอื่นแทน) เลยเปลี่ยนไปเช็คผิดตัว --
    กลับมาใช้ "ProceedCommand" ของ Alert นี้ตามเดิมแล้ว
    """
    if is_control_visible(
        window, timeout=timeout, auto_id="ProceedCommand", control_type="Button"
    ):
        print("[DEBUG] พบ Alert รหัสไปรษณีย์ครอบคลุมหลายพื้นที่ -> กด 'ดำเนินการ'")
        wait_and_click(window, auto_id="ProceedCommand", control_type="Button")
        


def handle_customer_capture_postal_code_alert(window, timeout=8):
    """
    Alert คนละตัวกับ handle_postcode_overlap_alert() ด้านบน -- ตัวนี้โผล่
    ขึ้นมาที่หน้า "ข้อมูลผู้ส่ง/ผู้รับ" (EG.CustomerCapture.CustomerCaptureView)
    ถ้ารหัสไปรษณีย์ในหน้านั้นไม่ตรงกับรหัสที่ระบบแนะนำ ยืนยันจาก controls
    dump จริงแล้ว: title="Alert", auto_id="EG.CustomerCapture.PostalCodeAlert"
    มี 2 ปุ่ม:
    - auto_id="PostalCodeAlertAcceptCommand" ("ตกลง", hotkey ENTER)
      = เปลี่ยนไปใช้รหัสที่ระบบแนะนำ (ไม่ต้องการ)
    - auto_id="PostalCodeAlertDeclineCommand" ("ยกเลิก", hotkey ESC)
      = คงรหัสไปรษณีย์เดิมที่พิมพ์เอง (ต้องการอันนี้)

    เรียกใช้ตรงช่วง "3x click_next" ก่อนเข้าหน้าค้นหาที่อยู่ เพราะ Alert นี้
    คือสาเหตุที่แท้จริงของหน้า "ข้อมูลผู้ส่ง" ที่เคยค้าง (กด Submit ไม่ติด
    เพราะโดน Alert บังอยู่) -- เช็คแบบเบาๆ ไม่เจอก็ข้ามไปเงียบๆ ไม่ throw
    """
    if is_control_visible(
        window,
        timeout=timeout,
        auto_id="PostalCodeAlertDeclineCommand",
        control_type="Button",
    ):
        print("[DEBUG] พบ Alert รหัสไปรษณีย์ (หน้าข้อมูลผู้ส่ง) -> กด 'ยกเลิก' (คงรหัสเดิม)")
        wait_and_click(
            window,
            auto_id="PostalCodeAlertDeclineCommand",
            control_type="Button",
        )
        


def click_next(window):
    """
    กดปุ่มถัดไป/ยืนยัน (ปุ่มหลักของหน้า)
    ลองใช้ auto_id="LocalCommand_Submit" ก่อน (เชื่อถือได้กว่า title ภาษาไทย
    ที่เพี้ยนจาก UI Automation) ถ้าไม่เจอค่อย fallback ไปหา title "ถัดไป"
    """
    try:
        wait_and_click(
            window,
            auto_id=SUBMIT_AUTO_ID,
            control_type="Button",
            wait_states="exists visible",
            timeout=3 ,
        )
    except Exception:
        print("[DEBUG] ไม่พบปุ่มด้วย auto_id, ลอง fallback เป็น title_re='ถัดไป'")
        # แก้: ต้องมี control_type="Button" เสมอ -- ไม่งั้น title_re จะ
        # แมตช์ทั้งตัว Button และ Static ลูก auto_id="CaptionTextBlock" ที่
        # โชว์ข้อความเดียวกัน กลายเป็น ElementAmbiguousError (เคยพังมาแล้ว
        # จริงจากจุดเดียวกันนี้)
        wait_and_click(window, title_re=r"^ถัดไป$", control_type="Button")



def get_main_pane_auto_id(window):
    """
    แก้: ฟังก์ชันนี้เคยหายไปด้วยเช่นกัน คืน auto_id ของ pane เนื้อหาหลัก
    (title="Main") ของหน้าปัจจุบัน เช่น "EG.Shipping.MailPieceCategory",
    "EG.CustomerCapture.CustomerCaptureView" -- ยืนยันจาก controls dump จริง
    แล้วว่า title="Main" คงที่ทุกหน้า มีแค่ auto_id ที่เปลี่ยนไปตามหน้า ใช้เป็น
    "ลายนิ้วมือ" เช็คว่าหน้าเปลี่ยนจริงหรือไม่หลังกดถัดไป คืน None ถ้าหาไม่เจอ
    """
    try:
        main_pane = window.child_window(title="Main", control_type="Custom")
        return main_pane.wrapper_object().element_info.automation_id
    except Exception:
        return None


def click_next_verified(window, max_attempts=3, settle_time=0.5):
    """
    แก้: ฟังก์ชันนี้เคยหายไปด้วยเช่นกัน -- ผู้ใช้สังเกตเจอว่าบางครั้งกด
    "ถัดไป" แล้วปุ่ม "ไม่ติด" จริง (หน้าไม่เปลี่ยน) โดยเฉพาะหน้าข้อมูลผู้ส่ง
    (customer) ที่บางครั้งค้างนิ่ง แต่ click_next() เดิมไม่เคยเช็คว่าหน้า
    เปลี่ยนจริงหรือเปล่า เลยเดินหน้าไปเรียกฟังก์ชันถัดไป (เช่น กรอกที่อยู่)
    ทั้งที่ยังอยู่หน้าเดิม -> เกิด error ตามมา

    เช็ค auto_id ของ pane "Main" ก่อน/หลังกด ถ้ายังไม่เปลี่ยนให้ลองกดซ้ำ
    (สูงสุด max_attempts ครั้ง) ถ้าลองครบแล้วยังไม่เปลี่ยน ให้แค่เตือนแล้ว
    ปล่อยผ่านไปเลย (ไม่ throw หยุดสคริปต์ -- ตามที่ตกลงกันไว้ว่าข้ามได้ ไม่ต้อง
    กรอกอะไรในหน้านี้)

    แก้: เจอ settle_time โดนแก้เป็น 5 (จากการแก้ไฟล์เอง) อันตรายมาก เพราะ
    ตัวนี้คือ time.sleep() จริง ไม่ใช่เพดาน .wait() แบบ timeout ตัวอื่นในไฟล์
    นี้ -- รันเต็มจำนวนทุกครั้งไม่ว่าหน้าจะเปลี่ยนเร็วแค่ไหน และฟังก์ชันนี้ถูก
    เรียกในลูป "3x" ทุกแถว เท่ากับเสียเวลาแน่นอนอย่างน้อย 3x5=15 วิ/แถว แบบ
    หนีไม่พ้น (ต่างจาก timeout เพดานอื่นๆ ที่ถ้าหน้าเปลี่ยนเร็วจะไม่กระทบเลย)
    ปรับกลับเป็น 0.5 ห้ามขึ้นสูงอีกเพราะกระทบความเร็วโดยตรงจริง
    """
    page_before = get_main_pane_auto_id(window)

    for attempt in range(1, max_attempts + 1):
        click_next(window)
        time.sleep(settle_time)
        page_after = get_main_pane_auto_id(window)

        if page_after != page_before or page_after is None:
            return True

        print(
            f"[WARNING] กดถัดไปแล้วหน้ายังไม่เปลี่ยน (auto_id เดิม={page_before!r}) "
            f"ลองกดซ้ำ ({attempt}/{max_attempts})"
        )

    print(
        "[WARNING] กดถัดไปครบ "
        f"{max_attempts} ครั้งแล้วหน้ายังไม่เปลี่ยน -- ข้ามไปเลยตามที่ตกลงกันไว้ "
        "(ไม่ให้สคริปต์ค้าง)"
    )
    return False


def report_validation_errors(window, timeout=1):
    """
    บางหน้า (เช่น ข้อมูลผู้รับ) มี ListBox auto_id="ValidationErrors" ที่โชว์
    ข้อความ error ถ้ากรอกข้อมูลไม่ครบ/ไม่ผ่าน validation -- เช็คแบบเบาๆ
    (timeout สั้น) หลังกด submit เผื่อมี จะได้ print ออกมาให้เห็นเลยว่าขาด
    ช่องไหน แทนที่จะต้องเดา/ขอ dump ใหม่ทุกครั้ง ไม่เจอก็ผ่านไปเงียบๆ
    """
    try:
        error_list = window.child_window(auto_id="ValidationErrors", control_type="List")
        error_list.wait("exists visible", timeout=timeout)
        wrapper = error_list.wrapper_object()
        items = wrapper.descendants()
        messages = [item.window_text() for item in items if item.window_text().strip()]
        if messages:
            print(f"[WARNING] พบ validation error บนหน้านี้: {messages}")
    except Exception:
        pass


def search_and_select_address(window, primary_search_term, timeout_per_try=7):
    """
    ค้นหาที่อยู่แล้วเลือกผลลัพธ์แรก -- ลอง primary_search_term (จาก CSV หรือ
    DEFAULT_ADDRESS_SEARCH) ก่อน ถ้าค้นแล้วไม่มีผลลัพธ์เลย (เช่นรหัสไปรษณีย์
    แถวนี้ไม่มีเลขที่ตรงกับที่ลองค้น) ให้ไล่ลองค่าถัดไปใน
    ADDRESS_SEARCH_FALLBACK_CANDIDATES จนกว่าจะเจอ หรือหมดรายการ
    """
    search_terms = [primary_search_term] + [
        term for term in ADDRESS_SEARCH_FALLBACK_CANDIDATES if term != primary_search_term
    ]

    last_error = None
    for term in search_terms:
        print(f"[DEBUG] กำลังค้นหาที่อยู่ด้วยคำว่า {term!r}")
        try:
            # แก้: force_type_keys=True เพราะช่องนี้เป็น search-as-you-type
            # ถ้าใช้ set_edit_text() (ตั้งค่าตรงผ่าน UIA ไม่ใช่จำลอง
            # keyboard event จริง) แอปจะไม่รู้ว่ามีการพิมพ์เกิดขึ้น เลยไม่
            # trigger ค้นหาให้เลย ทั้งที่ค่าที่โชว์ในช่องถูกต้อง
            fill_edit(
                window,
                term,
                title_re=r"^ที่อยู่$",
                auto_id="LabelForTextBox",
                force_type_keys=True,
            )
            

            # แก้: พิมพ์คำค้นหาอย่างเดียวไม่พอ ต้องกด "ถัดไป"/submit ก่อน
            # หน้าผลลัพธ์ถึงจะขึ้น (ผู้ใช้ทดสอบด้วยมือแล้วยืนยันตรงนี้)
            click_next(window)
            

            address_result_group = window.child_window(
                auto_id="AddressResult", control_type="Group"
            )
            address_result_group.wait("exists visible", timeout=timeout_per_try)

            first_address_result = address_result_group.child_window(
                control_type="ListItem", found_index=0
            )
            first_address_result.wait("exists visible", timeout=timeout_per_try)
            first_address_result.wrapper_object().click_input()
            

            print(f"[DEBUG] ค้นหาที่อยู่ด้วยคำว่า {term!r} เจอผลลัพธ์ -> เลือกตัวแรกแล้ว")
            return True

        except Exception as error:
            last_error = error
            print(f"[DEBUG] ค้นหาที่อยู่ด้วยคำว่า {term!r} ไม่เจอผลลัพธ์ ลองคำถัดไป")
            # แก้: เจอจริงว่าถ้าลองคำค้นหาติดกันเร็วเกินไปหลังไม่เจอผลลัพธ์
            # ช่องค้นหาจะเข้าสถานะ disabled ชั่วคราว ทำให้พิมพ์คำถัดไปไม่ติด
            # เลย (ElementNotEnabled) แทนที่จะแค่ "ไม่เจอผลลัพธ์" แบบปกติ พัก
            # สั้นๆ ก่อนลองคำถัดไป ให้ UI settle ก่อน (จ่ายแค่ตอนคำแรกๆ ไม่เจอ
            # ผลลัพธ์เท่านั้น ไม่กระทบกรณีปกติที่เจอผลลัพธ์ตั้งแต่คำแรก)
            time.sleep(0.5)

    print(f"[ERROR] ลองค้นหาที่อยู่ทุกคำใน {search_terms} แล้วไม่เจอผลลัพธ์เลย")
    if last_error:
        raise last_error
    raise RuntimeError("ค้นหาที่อยู่ไม่เจอผลลัพธ์เลยสักคำ")


def validate_csv_headers(fieldnames):
    """ตรวจสอบว่า CSV มี Header ที่จำเป็นครบหรือไม่"""
    required_headers = {"PostalCode", "FirstName", "LastName"}
    actual_headers = set(fieldnames or [])
    missing_headers = required_headers - actual_headers

    if missing_headers:
        missing_text = ", ".join(sorted(missing_headers))
        raise ValueError(
            f"CSV ขาด Header ที่จำเป็น: {missing_text}\n"
            f"Header ที่พบ: {fieldnames}"
        )

    optional_headers = {"Address", "Phone", "Weight"}
    missing_optional = optional_headers - actual_headers
    if missing_optional:
        missing_text = ", ".join(sorted(missing_optional))
        print(
            f"[WARNING] ไม่พบคอลัมน์ที่แนะนำให้เพิ่ม: {missing_text} "
            f"-> จะใช้ค่า default แทนสำหรับคอลัมน์ที่ขาด"
        )




def is_control_visible(window, timeout=1.5, **criteria):
    """เช็คว่า control ปรากฏอยู่จริงหรือไม่ โดยไม่ throw ถ้าไม่เจอ"""
    try:
        control = window.child_window(**criteria)
        control.wait("exists visible", timeout=timeout)
        return True
    except Exception:
        return False


def write_output_csv(rows, fieldnames, filename=OUTPUT_CSV_FILENAME):
    """
    แก้: ฟังก์ชันนี้เคยหายไปจากไฟล์ (โดนลบพร้อมกับ 'โค้ดที่ไม่จำเป็น' รอบก่อน)
    ทั้งที่ยังถูกเรียกใช้อยู่จริงใน main() -- เขียนไฟล์ CSV output ใหม่ทั้งไฟล์
    (มีคอลัมน์ TrackingNo เติมกลับเข้าไป) ทุกครั้งที่ทำรายการสำเร็จ เปิดด้วย
    Excel ดูได้เลยระหว่างที่สคริปต์ยังรันอยู่
    """
    try:
        with open(filename, mode="w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as error:
        print(f"[WARNING] เขียนไฟล์ {filename} ไม่สำเร็จ: {error}")


def wait_for_success(window, timeout=SUCCESS_WAIT_TIMEOUT):
    """
    แก้: เจอหลักฐานจริงแล้วว่า SUCCESS_TITLE_RE เดิม (หาข้อความ "สำเร็จ/
    เสร็จสิ้น/พิมพ์เสร็จ") ไม่เคยถูกต้องเลยตั้งแต่แรก (ในไฟล์เคยมี TODO
    ค้างบอกตรงๆ ว่ายังไม่เคยเอาไปเทียบกับ controls dump จริงเลย) ยืนยันจาก
    dump จริงว่าหลังพิมพ์เสร็จ แอปไม่มีหน้า/ข้อความ "สำเร็จ" ใดๆ เลย แต่กลับ
    ไปหน้า Menu.MainMenu ทันที (pane "Main" auto_id="Menu.MainMenu") พร้อม
    เลขพัสดุที่เพิ่งพิมพ์ถูกเพิ่มเข้า RetailStackView (ตะกร้ารายการที่ยังไม่
    Settle) -- แปลว่าที่ผ่านมาพิมพ์สำเร็จทุกใบจริง แต่สคริปต์คิดว่าล้มเหลว
    ทุกครั้ง เพราะหาข้อความที่ไม่มีทางเจอ เลยไม่เคยบันทึก log เลย

    เปลี่ยนมาเช็คว่ากลับมาที่ Menu.MainMenu แล้วหรือยังแทน (ผ่าน
    get_main_pane_auto_id()) เป็นสัญญาณที่ยืนยันจาก dump จริง ไม่ใช่เดา
    ห้ามลด timeout นี้ต่ำเกินไป (ดูคำเตือนตรง SUCCESS_WAIT_TIMEOUT ด้านบนไฟล์)
    """
    print("[DEBUG] กำลังตรวจสอบว่ากลับมาหน้าเมนูหลักแล้วหรือยัง (สัญญาณความสำเร็จ)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if get_main_pane_auto_id(window) == MAIN_MENU_AUTO_ID:
            print("[DEBUG] พบสัญญาณความสำเร็จ (กลับมาหน้าเมนูหลักแล้ว)")
            return True
        time.sleep(0.2)

    print("[WARNING] ไม่พบสัญญาณความสำเร็จภายในเวลาที่กำหนด")
    dump_controls_on_failure(window, "success_screen")
    return False


def capture_tracking_number(window, timeout=5):
    """
    แก้: เดิมอ่านจาก auto_id="SummaryView" แต่ยืนยันจาก dump จริงแล้วว่าพอ
    กลับมาหน้า Menu.MainMenu (สัญญาณความสำเร็จตัวใหม่ ดู wait_for_success())
    หน้า SummaryView จะไม่มีอยู่แล้ว -- เลขพัสดุที่เพิ่งพิมพ์จะถูกเพิ่มเข้า
    RetailStackView (ตะกร้ารายการที่ยังไม่ Settle) แทน เปลี่ยนมาอ่านจากตรงนั้น
    เอาตัวสุดท้ายในลิสต์ (เพิ่งเพิ่มล่าสุด) ใช้ TRACKING_NUMBER_RE แมตช์แทน
    การหา label ภาษาไทย (มักเพี้ยนผ่าน UI Automation) คืน None ถ้าหาไม่เจอ
    (ไม่ throw หยุดสคริปต์)
    """
    try:
        stack_view = window.child_window(
            auto_id="RetailStackView", control_type="Custom"
        )
        stack_view.wait("exists visible", timeout=timeout)
        wrapper = stack_view.wrapper_object()

        matches = []
        for item in wrapper.descendants():
            text = item.window_text()
            if text and TRACKING_NUMBER_RE.match(text.strip()):
                matches.append(text.strip())

        if matches:
            tracking_number = matches[-1]
            print(f"[DEBUG] พบเลขพัสดุ: {tracking_number}")
            return tracking_number

        print("[WARNING] หาเลขพัสดุใน RetailStackView ไม่เจอ")
        return None

    except Exception as error:
        print(f"[WARNING] อ่านเลขพัสดุไม่สำเร็จ: {error}")
        return None


def recover_ui(main_window, max_attempts=5):
    """
    พยายามกลับสู่หน้าแรก โดยลองกดปุ่ม "หน้าหลัก" (LocalCommand_Home) ก่อน
    เพราะน่าเชื่อถือกว่าการกด ESC วนหลายรอบ ถ้าไม่สำเร็จค่อย fallback เป็น ESC
    """
    print("[DEBUG] กำลังพยายามกู้คืนหน้าจอ")

    try:
        main_window.set_focus()
    except Exception:
        pass

    # วิธีที่ 1: กดปุ่ม "หน้าหลัก" โดยตรง
    try:
        home_button = main_window.child_window(
            auto_id=HOME_BUTTON_AUTO_ID, control_type="Button"
        )
        home_button.wait("exists visible", timeout=2)
        home_button.wrapper_object().click_input()
        

        if is_control_visible(
            main_window,
            timeout=3,
            auto_id=HOME_AUTO_ID,
            control_type=HOME_CONTROL_TYPE,
        ):
            print("[DEBUG] กลับมาหน้าแรกสำเร็จ (ผ่านปุ่มหน้าหลัก)")
            return True
    except Exception as error:
        print(f"[DEBUG] กดปุ่มหน้าหลักไม่สำเร็จ: {error}")

    # วิธีที่ 2: fallback เป็นการกด ESC วนหลายรอบ
    for attempt in range(1, max_attempts + 1):
        send_keys("{ESC}")
        

        if is_control_visible(
            main_window,
            timeout=1,
            auto_id=HOME_AUTO_ID,
            control_type=HOME_CONTROL_TYPE,
        ):
            print(f"[DEBUG] กลับมาหน้าแรกสำเร็จ (ESC ครั้งที่ {attempt})")
            return True

    print(
        "[ERROR] กู้คืนหน้าจอไม่สำเร็จ ไม่พบหน้าแรกหลังลองทั้งปุ่มหน้าหลักและ ESC "
        f"{max_attempts} ครั้ง -- ควรหยุดสคริปต์และตรวจสอบหน้าจอด้วยตนเอง"
    )
    return False


def export_controls(main_window):
    """บันทึกรายชื่อ control ทั้งหมดลง controls.txt (ใช้ตรวจ title/control_type/auto_id จริง)"""
    try:
        main_window.print_control_identifiers(filename=CONTROLS_FILENAME)
        print(f"[DEBUG] บันทึกรายชื่อ control ลง {CONTROLS_FILENAME} แล้ว")
    except Exception as error:
        print(f"[WARNING] ไม่สามารถสร้าง {CONTROLS_FILENAME} ได้: {error}")


def main():
    # แก้: เอา Timings.fast() ออก -- ทำให้เชื่อมต่อ/ค้างนานตอนเริ่มโปรแกรม
    # (สงสัยว่า retry interval ที่ถี่เกินไปชนกับปัญหา COM/UI Automation
    # ไม่เสถียรของแอป Riposte เอง ที่เคยเจอ error "COM event unable to
    # invoke subscribers" มาก่อนหน้านี้แล้วตอน dump control tree)
    # กลับไปใช้ค่า default ของ pywinauto แทน

    completed_names = load_processed_data()

    print(f"พบประวัติที่ทำสำเร็จแล้ว: {len(completed_names)} รายการ")
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")

    try:
        # แก้: title_re=".*Riposte.*" ยังชนกัน 2 ตัวแม้ใส่ visible_only=True
        # แล้ว (แปลว่ามีหน้าต่างที่มองเห็นอยู่จริง ชื่อมีคำว่า Riposte ซ้อนกัน
        # 2 อันจริงๆ) เปลี่ยนมาค้นด้วย auto_id="ECPMainWindow" แทน เพราะจาก
        # controls dump ทุกครั้งที่ผ่านมา auto_id นี้เจาะจงเฉพาะหน้าต่างหลัก
        # ตัวจริงเท่านั้น (child_window(title="Riposte POS Application",
        # auto_id="ECPMainWindow", control_type="Window"))
        app = Application(backend="uia").connect(
            auto_id="ECPMainWindow", timeout=5, visible_only=True
        )
        main_window = app.window(auto_id="ECPMainWindow", visible_only=True)
        main_window.wait("exists visible", timeout=5)
        main_window.set_focus()
        export_controls(main_window)

    except findwindows.ElementAmbiguousError:
        print(
            "เชื่อมต่อโปรแกรมไม่ได้: มีหน้าต่างหลักของ Riposte เปิดอยู่จริง "
            "มากกว่า 1 หน้าต่างพร้อมกัน (ลองเช็ค taskbar ว่าเปิด Riposte "
            "ซ้อนกันกี่หน้าต่าง) กรุณาปิดหน้าต่างที่ไม่ได้ใช้ทิ้งให้เหลือ "
            "หน้าต่างเดียว แล้วรันสคริปต์ใหม่"
        )
        traceback.print_exc()
        return

    except Exception:
        print("เชื่อมต่อโปรแกรมไม่ได้ กรุณาตรวจสอบว่าเปิด Riposte อยู่")
        traceback.print_exc()
        return

    print(f"กำลังเปิดไฟล์ข้อมูล {CSV_FILENAME}...")

    try:
        with open(
            CSV_FILENAME, mode="r", encoding="utf-8-sig", newline=""
        ) as csv_file:

            csv_reader = csv.DictReader(csv_file)
            validate_csv_headers(csv_reader.fieldnames)

            # แก้: โหลดทุกแถวเข้า memory ก่อน (ไม่ได้ stream ทีละแถวแบบเดิม)
            # เพื่อให้เติมค่า TrackingNo กลับเข้าไปในแถวที่ทำสำเร็จ แล้วเขียน
            # ออกเป็นไฟล์ CSV แยก (OUTPUT_CSV_FILENAME) ได้ระหว่างรัน
            rows = list(csv_reader)
            output_fieldnames = list(csv_reader.fieldnames or [])
            if "TrackingNo" not in output_fieldnames:
                output_fieldnames.append("TrackingNo")

            with open(LOG_FILENAME, mode="a", encoding="utf-8-sig") as log_file:

                for index, row in enumerate(rows, start=1):
                    zip_code = clean_value(row.get("PostalCode"))
                    first_name = clean_value(row.get("FirstName"))
                    last_name = clean_value(row.get("LastName"))

                    # แก้: ดึงค่าจาก CSV ถ้ามี ไม่งั้น fallback ไปค่า default
                    address_search = value_or_default(
                        row.get("Address"), DEFAULT_ADDRESS_SEARCH
                    )
                    phone_number = value_or_default(
                        row.get("Phone"), DEFAULT_PHONE_NUMBER
                    )
                    weight = value_or_default(
                        row.get("Weight"), DEFAULT_WEIGHT
                    )

                    unique_identifier = f"{first_name}|{last_name}|{zip_code}"

                    if not zip_code or not first_name or not last_name:
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            "PostalCode, FirstName หรือ LastName ไม่ครบ ---"
                        )
                        continue

                    if unique_identifier in completed_names:
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            f"{first_name} {last_name} (ทำไปแล้ว) ---"
                        )
                        continue

                    print(f"--- กำลังทำรายการที่ {index}: {first_name} {last_name} ---")

                    try:
                        # แก้: ลด "enabled" ออก เหลือแค่ "exists visible"
                        # (แอปนี้รายงานสถานะ enabled ช้า/ไม่แน่นอนหลังพิมพ์
                        # เสร็จ ทำให้จุดนี้เป็นจุดที่รอนานที่สุดตอนวนรอบใหม่
                        # -- ผู้ใช้สังเกตเจอ ยืนยันแล้วว่าไม่จำเป็นต้องรอ
                        # enabled จริงๆ)
                        main_window.wait("exists visible", timeout=5)
                        main_window.set_focus()

                        # หน้าเริ่มต้น (แก้: ใช้ auto_id แทน title ภาษาไทยที่เพี้ยน
                        # และผ่อนเงื่อนไขเป็น exists+visible เพราะ ListItem
                        # ในแอปนี้ไม่รายงานสถานะ enabled ผ่าน UI Automation)
                        wait_and_click(
                            main_window,
                            auto_id=HOME_AUTO_ID,
                            control_type=HOME_CONTROL_TYPE,
                            wait_states="exists visible",
                        )

                        # แก้: กู้คืน handle_repeat_transaction_alert() ที่
                        # หายไปจากไฟล์ (โดนลบพร้อมกับค่าคงที่
                        # REPEAT_TRANSACTION_ALERT_YES_AUTO_ID และตัวฟังก์ชัน
                        # เอง) กลับมาที่จุดนี้เหมือนเดิม
                        handle_repeat_transaction_alert(main_window)

                        wait_and_click(
                            main_window,
                            auto_id=BOX_TYPE_AUTO_ID,
                            control_type="ListItem",
                            wait_states="exists visible",
                        )

                        click_next(main_window)  # ถัดไป (หลังเลือกกล่อง)

                        # แก้: หน้าคำถามสินค้าอันตรายแทรกมาตรงนี้ (ถ้ามี)
                        handle_dangerous_goods_question(main_window)

                        click_next(main_window)  # ยืนยัน (ปุ่มเดียวกัน auto_id)

                        # น้ำหนัก
                        # แก้: เพิ่ม auto_id="LabelForTextBox" ระบุให้เจาะจงว่า
                        # เอา label ของช่องกรอก ไม่ใช่ label หัวข้อหน้า (Title)
                        # ที่ข้อความ "น้ำหนัก" ซ้ำกันอยู่ทั้งสองที่ (ยืนยันจาก
                        # controls dump หน้า EG.Shipping.Weight) แล้ว
                        # resolve_edit_wrapper() จะไต่ไปหา Edit ข้างเคียงให้เอง
                        fill_edit(
                            main_window,
                            weight,
                            title_re=r".*น้ำหนัก.*",
                            auto_id="LabelForTextBox",
                        )
                        click_next(main_window)

                        # รหัสไปรษณีย์
                        fill_edit(
                            main_window,
                            zip_code,
                            title_re=r".*ระบุรหัสไปรษณีย์?.*",
                            auto_id="LabelForTextBox",
                        )
                        click_next(main_window)

                        # แก้: รหัสไปรษณีย์บางเลขครอบคลุมหลายพื้นที่ จะมี
                        # Alert แทรกถามให้ยืนยัน (ถ้ามี)
                        handle_postcode_overlap_alert(main_window)

                        # เลือกบริการ -- ยืนยันจาก controls dump จริงแล้วว่า
                        # ปุ่มที่ต้องกดคือ auto_id="ShippingService_2572"
                        # (เลิกใช้ found_index=0 guess และ hotkey "0" แบบเดิม)
                        # แก้: เจอสาเหตุจริงของบั๊ก "หยุดนิ่งแล้ว ESC กลับหน้าแรก"
                        # จาก traceback จริงแล้ว -- ไม่ใช่ timeout ของ
                        # handle_postcode_overlap_alert() (อันนั้นกด
                        # ProceedCommand สำเร็จปกติ) แต่เป็นจุดนี้: ไม่เคยระบุ
                        # timeout= มาก่อน เลยใช้ default=5 วิ ซึ่งไม่พอ เพราะ
                        # หลังกดปิด Alert แอปต้องเปลี่ยนหน้า/โหลดปุ่มบริการ
                        # ~39 ปุ่ม บางครั้งเกิน 5 วิ -> control.wait() timeout
                        # ก่อนถึง click_input() เลย (เม้าเลยไม่ขยับ) แล้ว
                        # โดน except ด้านบนจับ -> recover_ui() ESC กลับหน้าแรก
                        # เพิ่มเป็น 10 วิให้เผื่อการโหลดหน้านี้โดยเฉพาะ
                        wait_and_click(
                            main_window,
                            auto_id=SHIPPING_SERVICE_AUTO_ID,
                            control_type="Button",
                            wait_states="exists visible",
                            timeout=10,
                        )

                        # แก้: ช่วงนี้มีโอกาสเจอหน้า "ข้อมูลผู้ส่ง" (customer
                        # ที่มาใช้บริการ) แทรกมา บางครั้งกดถัดไปแล้วหน้าไม่
                        # เปลี่ยนจริง (ผู้ใช้สังเกตเจอ) -- ตอนนี้รู้สาเหตุจริง
                        # แล้ว: หน้านั้นมี Alert รหัสไปรษณีย์
                        # (EG.CustomerCapture.PostalCodeAlert) บังปุ่ม Submit
                        # อยู่ ทำให้กดไม่ติด เช็ค/ปิด Alert นี้ก่อนทุกรอบ แล้ว
                        # ค่อยใช้ click_next_verified() (เช็คว่าหน้าเปลี่ยน
                        # จริงก่อนไปต่อ ไม่กรอกอะไรในหน้านี้ ข้ามได้เลยตามที่
                        # ตกลง)
                        for round_number in range(1, 4):
                            print(f"[DEBUG] กดถัดไป รอบที่ {round_number}/3")
                            handle_customer_capture_postal_code_alert(main_window)
                            click_next_verified(main_window)

                        # ค้นหาและเลือกที่อยู่ (แก้: ใช้ address_search จาก CSV
                        # เป็นคำค้นหาแรก ถ้าไม่เจอผลลัพธ์ จะไล่ลองคำถัดไปใน
                        # ADDRESS_SEARCH_FALLBACK_CANDIDATES ให้เอง เพราะข้อมูล
                        # เป็น mock ไม่ใช่ที่อยู่จริง เลขที่เดียวอาจไม่ตรงกับ
                        # ทุกรหัสไปรษณีย์)
                        search_and_select_address(main_window, address_search)
                        click_next(main_window)

                        # ข้อมูลผู้รับ
                        # แก้: เจอจาก controls dump จริงของหน้านี้
                        # (EG.CustomerCapture.CustomerCaptureView) ว่าช่อง Edit
                        # แต่ละช่องมี auto_id ภาษาอังกฤษตรงตัวอยู่แล้ว
                        # (CustomerFirstName, CustomerLastName, PhoneNumber)
                        # ไม่ต้องพึ่ง title_re ภาษาไทยที่เพี้ยน (mojibake) อีก
                        # ต่อไป -- ยิงตรง auto_id เลย แม่นกว่าและเร็วกว่า

                        # แก้: หน้านี้มีช่อง PostalCode ของตัวเอง (คนละช่องกับ
                        # หน้า Destination ก่อนหน้า) พบว่าตอนทำรายการซ้ำ ค่า
                        # เก่าจากรายการก่อนหน้าจะค้างอยู่ในช่องนี้ -- กรอกทับ
                        # ด้วย zip_code ตรงๆ เลย ไม่พึ่งให้ search_and_select_
                        # address() sync ให้เอง (ไม่ชัวร์ว่า sync จริงหรือ
                        # เปล่า) ป้องกันใบปะหน้าออกมาผิดรหัสไปรษณีย์
                        fill_edit(
                            main_window,
                            zip_code,
                            auto_id="PostalCode",
                            control_type="Edit",
                        )

                        fill_edit(
                            main_window,
                            first_name,
                            auto_id="CustomerFirstName",
                            control_type="Edit",
                        )
                        fill_edit(
                            main_window,
                            last_name,
                            auto_id="CustomerLastName",
                            control_type="Edit",
                        )
                        fill_edit(
                            main_window,
                            phone_number,  # แก้: ใช้เบอร์จาก CSV
                            auto_id="PhoneNumber",
                            control_type="Edit",
                        )

                        # แก้: หน้า "ข้อมูลผู้รับ" (EG.CustomerCapture.
                        # CustomerCaptureView) ต้องกด "ถัดไป" ยืนยันฟอร์มนี้
                        # ก่อน ถึงจะไปหน้า dialog "ไม่" ต่อได้ -- เดิมขาด
                        # ขั้นตอนนี้ไปเลยกดหา "ไม่" ไม่เจอ (ยืนยันจาก controls
                        # dump จริงแล้วว่าหน้านี้มีปุ่ม LocalCommand_Submit)
                        click_next(main_window)
                        report_validation_errors(main_window)

                        # สิ้นสุดกระบวนการ
                        # แก้: ต้องมี control_type="Button" เสมอ -- ไม่งั้น
                        # title_re จะแมตช์ทั้งตัว Button และ Static ลูก
                        # auto_id="CaptionTextBlock" ที่โชว์ข้อความเดียวกัน
                        # กลายเป็น ElementAmbiguousError (นี่คือจุดที่เคย
                        # พังจริงมาแล้วหลายรอบ ห้ามลบ control_type ตรงนี้ออก)
                        wait_and_click(
                            main_window, title_re=r"^ไม่$", control_type="Button"
                        )
                        time.sleep(0.1)

                        # แก้: ตรวจสอบหน้า success จริงก่อนบันทึก log
                        if not wait_for_success(main_window):
                            raise RuntimeError(
                                "ไม่พบสัญญาณยืนยันความสำเร็จ -- "
                                "จะไม่บันทึกรายการนี้ลง log"
                            )

                        # แก้: บล็อกนี้ทั้งหมด (จับเลขพัสดุ, บันทึก log,
                        # เขียน CSV output) เคยหายไปจากไฟล์ (โดนลบพร้อมกับ
                        # "โค้ดที่ไม่จำเป็น" รอบก่อน) เหลือแค่คอมเมนต์ไว้เฉยๆ
                        # ทำให้ completed_names ไม่เคยถูกอัปเดตเลย -- อันตราย
                        # มาก เพราะถ้ารันสคริปต์ใหม่ จะไม่รู้ว่ารายการไหนทำไป
                        # แล้วบ้าง เสี่ยงพิมพ์ใบซ้ำทุกใบตั้งแต่ต้น กู้คืนกลับมา

                        # แก้: อ่านเลขพัสดุ (tracking number) มาบันทึกไว้ด้วย
                        # เผื่ออ่านไม่ได้ ก็ยังถือว่ารายการนี้สำเร็จ (บันทึก
                        # ช่องเลขพัสดุว่างไว้ก่อน)
                        tracking_number = capture_tracking_number(main_window)

                        log_file.write(
                            f"{unique_identifier}|{tracking_number or ''}\n"
                        )
                        log_file.flush()
                        completed_names.add(unique_identifier)

                        # แก้: ตัด write_output_csv() ออกจากตรงนี้ตามที่ขอ
                        # (เพื่อ performance) -- เดิมเขียน CSV ใหม่ทั้งไฟล์ทุก
                        # แถวที่สำเร็จ ยิ่งรันไปนานยิ่งช้าขึ้นเรื่อยๆ (ไฟล์ใหญ่
                        # ขึ้นทุกรอบ) ย้ายไปเขียนครั้งเดียวตอนจบทั้งหมดแทน
                        # (ท้ายฟังก์ชัน main() ด้านล่าง) เก็บแค่ค่าไว้ใน memory
                        # ตรงนี้ (ไม่มี I/O เพิ่ม แทบไม่กินเวลาเลย)
                        row["TrackingNo"] = tracking_number or row.get("TrackingNo", "")

                        print(
                            f"ทำรายการที่ {index} สำเร็จ และบันทึกลง Log แล้ว "
                            f"(เลขพัสดุ: {tracking_number or 'ไม่พบ'})"
                        )

                    except PywinautoTimeoutError:
                        print(f"Timeout ที่รายการ {index}: {first_name} {last_name}")
                        traceback.print_exc()
                        if not recover_ui(main_window):
                            print("[FATAL] หยุดสคริปต์เพราะกู้คืนหน้าจอไม่สำเร็จ")
                            write_output_csv(rows, output_fieldnames)
                            return

                    except Exception as error:
                        print(f"เกิดข้อผิดพลาดที่รายการ {index}: {first_name} {last_name}")
                        print(f"ชนิด Error: {type(error).__name__}")
                        print(f"รายละเอียด: {error}")
                        traceback.print_exc()
                        if not recover_ui(main_window):
                            print("[FATAL] หยุดสคริปต์เพราะกู้คืนหน้าจอไม่สำเร็จ")
                            write_output_csv(rows, output_fieldnames)
                            return

                # แก้: เขียน CSV output ครั้งเดียวตอนจบ loop ทั้งหมด (ย้ายมาจาก
                # ในลูปตามที่ขอ เพื่อ performance -- ไม่ต้องเขียนไฟล์ซ้ำทุกแถว)
                write_output_csv(rows, output_fieldnames)

    except FileNotFoundError:
        print(f"ไม่พบไฟล์ {CSV_FILENAME} กรุณาตรวจสอบว่าไฟล์อยู่ในโฟลเดอร์เดียวกับสคริปต์")

    except PermissionError:
        print(f"ไม่สามารถเปิดไฟล์ {CSV_FILENAME} ได้ กรุณาปิดไฟล์ใน Excel แล้วลองใหม่")

    except ValueError as error:
        print(f"โครงสร้าง CSV ไม่ถูกต้อง: {error}")

    except Exception:
        print("เกิดข้อผิดพลาดขณะอ่านหรือประมวลผลไฟล์ CSV")
        traceback.print_exc()

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")


if __name__ == "__main__":
    main()