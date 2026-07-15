import csv
import os
import re
import subprocess
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

# แก้: push ไฟล์ output กลับขึ้น git repo เดิม (ที่เครื่องนี้ต่อ GitHub อยู่
# แล้ว) เป็นระยะ เพื่อให้ดึงไฟล์จากเครื่องอื่นได้ผ่าน git pull โดยไม่ต้อง
# setup อะไรเพิ่ม -- throttle ไม่ให้ push ถี่เกินไป (หน่วยเป็นวินาที)
GIT_SYNC_INTERVAL_SECONDS = 300

# ค่า default ใช้เมื่อ CSV ไม่มีคอลัมน์ หรือช่องนั้นว่าง
DEFAULT_PHONE_NUMBER = "0987654321"
DEFAULT_WEIGHT = "500"
DEFAULT_ADDRESS_SEARCH = "11"

# แก้: ค่าเดียว "88" ใช้ได้แค่กับรหัสไปรษณีย์ที่มีเลขที่ตรงพอดี (เจอปัญหาจริง
# ว่ารหัสไปรษณีย์อื่นค้นหา "88" แล้วไม่มีผลลัพธ์เลย) เนื่องจากเป็นข้อมูล mock
# ไม่ใช่ที่อยู่จริงของผู้รับ (ยืนยันจากผู้ใช้แล้วว่าใช้เลขที่ใกล้เคียงแทนได้)
# เลยลองไล่ทีละค่าจากรายการนี้แทน ค่าไหนเจอผลลัพธ์ก่อนก็ใช้ค่านั้น
ADDRESS_SEARCH_FALLBACK_CANDIDATES = ["11", "12", "88", "1", "2", "10"]

# ---------------------------------------------------------------
# TODO: หลังรันครั้งแรกแล้วเปิด controls.txt ขึ้นมาดู ให้หา title
# ของ control/ข้อความที่ปรากฏ "เฉพาะตอนพิมพ์สำเร็จ" เท่านั้น
# (เช่น ป้ายข้อความ "พิมพ์สำเร็จ", "เสร็จสิ้น", ปุ่ม "พิมพ์ใบปะหน้าใหม่" ฯลฯ)
# แล้วนำมาแทนที่ regex ด้านล่างนี้ให้ตรงกับของจริง
# ---------------------------------------------------------------
SUCCESS_TITLE_RE = r".*(สำเร็จ|เสร็จสิ้น|พิมพ์เสร็จ).*"
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
    """คืนค่าจาก CSV ถ้ามี ไม่งั้นใช้ค่า default"""
    cleaned = clean_value(value)
    return cleaned if cleaned else default


def dump_controls_on_failure(window, tag):
    """
    เมื่อหา control ไม่เจอ ให้ dump control tree ปัจจุบันลงไฟล์แยก
    เพื่อเทียบกับ title_re/regex ที่ใช้ค้นหา ช่วย debug ได้เร็วขึ้น
    """
    filename = f"controls_fail_{tag}.txt"
    try:
        window.print_control_identifiers(filename=filename)
        print(f"[DEBUG] บันทึก control tree ตอน fail ลง {filename} แล้ว "
              f"-> เปิดไฟล์นี้เทียบกับ title_re ที่ใช้ค้นหา")
    except Exception as dump_error:
        print(f"[WARNING] dump control tree ไม่สำเร็จ: {dump_error}")


def wait_and_click(window, timeout=15, wait_states="exists visible enabled", **criteria):
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


def resolve_edit_wrapper(wrapper, timeout=15):
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


def fill_edit(window, value, timeout=15, force_type_keys=False, **criteria):
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
        time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency)
        click_next(window)


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
            timeout=5,
        )
    except Exception:
        print("[DEBUG] ไม่พบปุ่มด้วย auto_id, ลอง fallback เป็น title_re='ถัดไป'")
        wait_and_click(window, title_re=r"^ถัดไป$")

    time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency, click_next โดนเรียกบ่อยสุด)


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


def search_and_select_address(window, primary_search_term, timeout_per_try=12):
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
            time.sleep(1)

            # แก้: พิมพ์คำค้นหาอย่างเดียวไม่พอ ต้องกด "ถัดไป"/submit ก่อน
            # หน้าผลลัพธ์ถึงจะขึ้น (ผู้ใช้ทดสอบด้วยมือแล้วยืนยันตรงนี้)
            click_next(window)
            time.sleep(1)

            address_result_group = window.child_window(
                auto_id="AddressResult", control_type="Group"
            )
            address_result_group.wait("exists visible", timeout=timeout_per_try)

            first_address_result = address_result_group.child_window(
                control_type="ListItem", found_index=0
            )
            first_address_result.wait("exists visible", timeout=timeout_per_try)
            first_address_result.wrapper_object().click_input()
            time.sleep(1)

            print(f"[DEBUG] ค้นหาที่อยู่ด้วยคำว่า {term!r} เจอผลลัพธ์ -> เลือกตัวแรกแล้ว")
            return True

        except Exception as error:
            last_error = error
            print(f"[DEBUG] ค้นหาที่อยู่ด้วยคำว่า {term!r} ไม่เจอผลลัพธ์ ลองคำถัดไป")

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


def write_output_csv(rows, fieldnames, filename=OUTPUT_CSV_FILENAME):
    """
    เขียนไฟล์ CSV แยกต่างหาก (ไม่แตะ data.csv ต้นฉบับ) พร้อมคอลัมน์
    TrackingNo ที่เติมค่าล่าสุดไว้ -- เขียนทับทั้งไฟล์ทุกครั้งที่เรียก
    (เรียกหลังทำแต่ละรายการสำเร็จ ปลอดภัยเพราะแต่ละรายการใช้เวลาหลายวินาที
    อยู่แล้วจาก UI automation ไม่ได้เขียนถี่จนกระทบ performance)
    """
    try:
        with open(filename, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as error:
        print(f"[WARNING] เขียนไฟล์ {filename} ไม่สำเร็จ: {error}")


_last_git_sync_time = 0


def maybe_sync_output_to_git():
    """
    push ไฟล์ output (data_with_tracking.csv, success_log.txt) กลับขึ้น git
    repo เดิมเป็นระยะ (throttle ไม่เกินทุก GIT_SYNC_INTERVAL_SECONDS) เพื่อให้
    ดึงไฟล์จากเครื่องอื่นได้ผ่าน git pull โดยไม่ต้อง setup TCP server เอง
    ถ้า git ไม่มี/push ไม่สำเร็จ (เช่น ไม่มีเน็ตตอนนั้น) แค่ print warning
    ไม่ throw เพื่อไม่ให้กระทบ automation หลัก -- ลองใหม่ได้ในรอบถัดไป
    """
    global _last_git_sync_time

    now = time.time()
    if now - _last_git_sync_time < GIT_SYNC_INTERVAL_SECONDS:
        return
    _last_git_sync_time = now

    try:
        subprocess.run(
            ["git", "add", OUTPUT_CSV_FILENAME, LOG_FILENAME],
            check=True, capture_output=True, timeout=15, text=True,
        )

        commit_message = f"auto: update output {time.strftime('%Y-%m-%d %H:%M:%S')}"
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True, timeout=15, text=True,
        )
        # แก้: commit อาจ "fail" ถ้าไม่มีอะไรเปลี่ยนเลยตั้งแต่รอบก่อน (ปกติ
        # ไม่ใช่ error จริง) เช็คจาก stdout แทนที่จะโยน exception มั่วๆ
        if commit_result.returncode != 0 and "nothing to commit" not in commit_result.stdout:
            print(f"[WARNING] git commit output: {commit_result.stdout} {commit_result.stderr}")
            return

        subprocess.run(
            ["git", "push"], check=True, capture_output=True, timeout=30, text=True,
        )
        print("[DEBUG] sync ไฟล์ output ขึ้น git แล้ว (ดึงจากเครื่องอื่นได้ด้วย git pull)")

    except Exception as error:
        print(f"[WARNING] sync ไฟล์ output ขึ้น git ไม่สำเร็จ: {error}")


def is_control_visible(window, timeout=3, **criteria):
    """เช็คว่า control ปรากฏอยู่จริงหรือไม่ โดยไม่ throw ถ้าไม่เจอ"""
    try:
        control = window.child_window(**criteria)
        control.wait("exists visible", timeout=timeout)
        return True
    except Exception:
        return False


def wait_for_success(window, timeout=SUCCESS_WAIT_TIMEOUT):
    """
    ตรวจสอบว่าถึงหน้า/ข้อความยืนยันความสำเร็จจริงหรือไม่
    ก่อนจะถือว่ารายการนี้ทำสำเร็จ
    """
    print("[DEBUG] กำลังตรวจสอบหน้าจอยืนยันความสำเร็จ...")
    if is_control_visible(window, timeout=timeout, title_re=SUCCESS_TITLE_RE):
        print("[DEBUG] พบสัญญาณความสำเร็จ")
        return True

    print("[WARNING] ไม่พบสัญญาณความสำเร็จภายในเวลาที่กำหนด")
    return False


def capture_tracking_number(window, timeout=5):
    """
    อ่านเลขพัสดุ (tracking number) จากแผง SummaryView (สรุปรายการฝั่งขวา)
    หลังพิมพ์ใบปะหน้าสำเร็จ -- แมตช์ด้วยรูปแบบเลขพัสดุเอง (TRACKING_NUMBER_RE)
    แทนการหา label ภาษาไทย "เลขที่พัสดุ" เพราะ label มักเพี้ยนผ่าน UI
    Automation เหมือนจุดอื่นๆ ที่เจอมา ถ้ามีหลายรายการใน cart (ยังไม่ Settle)
    เอาตัวล่าสุด (รายการที่เพิ่งพิมพ์เสร็จ น่าจะอยู่ท้ายสุด)
    """
    try:
        summary_view = window.child_window(auto_id="SummaryView", control_type="Custom")
        summary_view.wait("exists visible", timeout=timeout)
        wrapper = summary_view.wrapper_object()

        texts = [d.window_text().strip() for d in wrapper.descendants(control_type="Text")]
        matches = [t for t in texts if TRACKING_NUMBER_RE.match(t)]

        if matches:
            print(f"[DEBUG] พบเลขพัสดุ: {matches[-1]}")
            return matches[-1]

        print("[WARNING] ไม่พบเลขพัสดุใน SummaryView")
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
        home_button.wait("exists visible", timeout=3)
        home_button.wrapper_object().click_input()
        time.sleep(1)

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
        time.sleep(0.7)

        if is_control_visible(
            main_window,
            timeout=2,
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
            auto_id="ECPMainWindow", timeout=15, visible_only=True
        )
        main_window = app.window(auto_id="ECPMainWindow", visible_only=True)
        main_window.wait("exists visible", timeout=15)
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
                        main_window.wait("exists visible enabled", timeout=15)
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
                        time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency)

                        wait_and_click(
                            main_window,
                            auto_id=BOX_TYPE_AUTO_ID,
                            control_type="ListItem",
                            wait_states="exists visible",
                        )
                        time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency)

                        click_next(main_window)  # ถัดไป (หลังเลือกกล่อง)

                        # แก้: หน้าคำถามสินค้าอันตรายแทรกมาตรงนี้ (ถ้ามี)
                        handle_dangerous_goods_question(main_window)

                        click_next(main_window)  # ยืนยัน (ปุ่มเดียวกัน auto_id)
                        time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency)

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
                        time.sleep(1.5)  # แก้: ลดจาก 2 วิ (รายการบริการโหลดจากเซิร์ฟเวอร์ เผื่อไว้หน่อย)

                        # เลือกบริการ -- ยืนยันจาก controls dump จริงแล้วว่า
                        # ปุ่มที่ต้องกดคือ auto_id="ShippingService_2572"
                        # (เลิกใช้ found_index=0 guess และ hotkey "0" แบบเดิม)
                        wait_and_click(
                            main_window,
                            auto_id=SHIPPING_SERVICE_AUTO_ID,
                            control_type="Button",
                            wait_states="exists visible",
                        )
                        time.sleep(0.5)  # แก้: ลดจาก 1 วิ (ลด latency)

                        for round_number in range(1, 4):
                            print(f"[DEBUG] กดถัดไป รอบที่ {round_number}/3")
                            click_next(main_window)

                        # ค้นหาและเลือกที่อยู่ (แก้: ใช้ address_search จาก CSV
                        # เป็นคำค้นหาแรก ถ้าไม่เจอผลลัพธ์ จะไล่ลองคำถัดไปใน
                        # ADDRESS_SEARCH_FALLBACK_CANDIDATES ให้เอง เพราะข้อมูล
                        # เป็น mock ไม่ใช่ที่อยู่จริง เลขที่เดียวอาจไม่ตรงกับ
                        # ทุกรหัสไปรษณีย์)
                        search_and_select_address(main_window, address_search)
                        click_next(main_window)

                        # ข้อมูลผู้รับ
                        fill_edit(
                            main_window,
                            first_name,
                            title_re=r"^ชื่อ$",
                            auto_id="LabelForTextBox",
                        )
                        fill_edit(
                            main_window,
                            last_name,
                            title_re=r"^นามสกุล$",
                            auto_id="LabelForTextBox",
                        )
                        fill_edit(
                            main_window,
                            phone_number,  # แก้: ใช้เบอร์จาก CSV
                            title_re=r".*หมายเลขโทรศัพท์.*",
                            auto_id="LabelForTextBox",
                        )

                        # แก้: หน้า "ข้อมูลผู้รับ" (EG.CustomerCapture.
                        # CustomerCaptureView) ต้องกด "ถัดไป" ยืนยันฟอร์มนี้
                        # ก่อน ถึงจะไปหน้า dialog "ไม่" ต่อได้ -- เดิมขาด
                        # ขั้นตอนนี้ไปเลยกดหา "ไม่" ไม่เจอ (ยืนยันจาก controls
                        # dump จริงแล้วว่าหน้านี้มีปุ่ม LocalCommand_Submit)
                        click_next(main_window)
                        report_validation_errors(main_window)

                        # สิ้นสุดกระบวนการ
                        wait_and_click(main_window, title_re=r"^ไม่$")
                        time.sleep(2)

                        # แก้: ตรวจสอบหน้า success จริงก่อนบันทึก log
                        if not wait_for_success(main_window):
                            raise RuntimeError(
                                "ไม่พบสัญญาณยืนยันความสำเร็จ -- "
                                "จะไม่บันทึกรายการนี้ลง log"
                            )

                        # แก้: อ่านเลขพัสดุ (tracking number) มาบันทึกไว้ด้วย
                        # เผื่ออ่านไม่ได้ ก็ยังถือว่ารายการนี้สำเร็จ (บันทึก
                        # ช่องเลขพัสดุว่างไว้ก่อน)
                        tracking_number = capture_tracking_number(main_window)

                        log_file.write(
                            f"{unique_identifier}|{tracking_number or ''}\n"
                        )
                        log_file.flush()
                        completed_names.add(unique_identifier)

                        # แก้: เติมเลขพัสดุกลับเข้าแถวนี้ แล้วเขียนไฟล์ CSV
                        # output ใหม่ทั้งไฟล์ (เปิดด้วย Excel ดูได้เลย)
                        row["TrackingNo"] = tracking_number or row.get("TrackingNo", "")
                        write_output_csv(rows, output_fieldnames)

                        # แก้: push ไฟล์ output ขึ้น git เป็นระยะ ดึงจาก
                        # เครื่องอื่นได้ผ่าน git pull (throttle อยู่แล้วในตัว)
                        maybe_sync_output_to_git()

                        print(
                            f"ทำรายการที่ {index} สำเร็จ และบันทึกลง Log แล้ว "
                            f"(เลขพัสดุ: {tracking_number or 'ไม่พบ'})"
                        )

                    except PywinautoTimeoutError:
                        print(f"Timeout ที่รายการ {index}: {first_name} {last_name}")
                        traceback.print_exc()
                        if not recover_ui(main_window):
                            print("[FATAL] หยุดสคริปต์เพราะกู้คืนหน้าจอไม่สำเร็จ")
                            return

                    except Exception as error:
                        print(f"เกิดข้อผิดพลาดที่รายการ {index}: {first_name} {last_name}")
                        print(f"ชนิด Error: {type(error).__name__}")
                        print(f"รายละเอียด: {error}")
                        traceback.print_exc()
                        if not recover_ui(main_window):
                            print("[FATAL] หยุดสคริปต์เพราะกู้คืนหน้าจอไม่สำเร็จ")
                            return

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