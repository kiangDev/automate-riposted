import csv
import os
import time
import traceback

from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto.timings import TimeoutError as PywinautoTimeoutError


CSV_FILENAME = "data.csv"
LOG_FILENAME = "success_log.txt"
CONTROLS_FILENAME = "controls.txt"

PHONE_NUMBER = "0987654321"
DEFAULT_WEIGHT = "500"
DEFAULT_ADDRESS_SEARCH = "88"


def load_processed_data(log_filename=LOG_FILENAME):
    """อ่านรายการที่ทำสำเร็จแล้วจากไฟล์ log"""
    processed = set()

    if not os.path.exists(log_filename):
        return processed

    with open(log_filename, "r", encoding="utf-8-sig") as file:
        for line in file:
            identifier = line.strip()
            if identifier:
                processed.add(identifier)

    return processed


def clean_value(value):
    """แปลงค่า CSV เป็นข้อความและตัดช่องว่าง"""
    if value is None:
        return ""

    return str(value).strip()


def wait_and_click(window, timeout=15, **criteria):
    """
    รอให้ control ปรากฏและพร้อมใช้งาน แล้วคลิก

    ตัวอย่าง:
        wait_and_click(
            main_window,
            title_re=r".*รับฝากสิ่งของ.*",
        )
    """
    print(f"[DEBUG] กำลังค้นหา control: {criteria}")

    try:
        control = window.child_window(**criteria)

        # ไม่ใช้ ready เพราะ UIA บาง control ไม่รองรับสถานะนี้
        control.wait(
            "exists visible enabled",
            timeout=timeout,
        )

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
        raise


def fill_edit(window, value, timeout=15, **criteria):
    """
    รอช่องกรอก ล้างข้อมูลเดิม แล้วกรอกค่าใหม่
    """
    print(f"[DEBUG] กำลังค้นหาช่องกรอก: {criteria}")

    try:
        control = window.child_window(**criteria)
        control.wait(
            "exists visible enabled",
            timeout=timeout,
        )

        wrapper = control.wrapper_object()
        wrapper.click_input()

        print("[DEBUG] พบช่องกรอก")
        print(f"        title        = {wrapper.window_text()!r}")
        print(f"        control_type = {wrapper.element_info.control_type!r}")
        print(f"        automation_id= {wrapper.element_info.automation_id!r}")

        try:
            wrapper.set_edit_text(str(value))

        except Exception:
            send_keys("^a")
            send_keys("{BACKSPACE}")

            wrapper.type_keys(
                str(value),
                with_spaces=True,
                set_foreground=True,
            )

        return wrapper

    except Exception as error:
        print(f"[ERROR] กรอกข้อมูลไม่สำเร็จ: {criteria}")
        print(f"[ERROR] ค่าที่ต้องการกรอก: {value!r}")
        print(f"[ERROR] {type(error).__name__}: {error}")
        raise


def click_next(window):
    """กดปุ่มถัดไป"""
    wait_and_click(
        window,
        title_re=r"^ถัดไป$",
    )
    time.sleep(1)


def validate_csv_headers(fieldnames):
    """ตรวจสอบว่า CSV มี Header ที่จำเป็นครบหรือไม่"""
    required_headers = {
        "PostalCode",
        "FirstName",
        "LastName",
    }

    actual_headers = set(fieldnames or [])
    missing_headers = required_headers - actual_headers

    if missing_headers:
        missing_text = ", ".join(sorted(missing_headers))

        raise ValueError(
            f"CSV ขาด Header ที่จำเป็น: {missing_text}\n"
            f"Header ที่พบ: {fieldnames}"
        )


def recover_ui(main_window):
    """พยายามปิด popup และกลับสู่หน้าที่พร้อมทำรายการต่อ"""
    print("[DEBUG] กำลังพยายามกู้คืนหน้าจอด้วยปุ่ม ESC")

    try:
        main_window.set_focus()
    except Exception:
        pass

    for _ in range(3):
        send_keys("{ESC}")
        time.sleep(0.5)


def export_controls(main_window):
    """
    บันทึกรายชื่อ control ทั้งหมดลง controls.txt
    ใช้สำหรับตรวจ title, control_type และ auto_id จริง
    """
    try:
        main_window.print_control_identifiers(
            filename=CONTROLS_FILENAME
        )

        print(
            f"[DEBUG] บันทึกรายชื่อ control ลง "
            f"{CONTROLS_FILENAME} แล้ว"
        )

    except Exception as error:
        print(
            f"[WARNING] ไม่สามารถสร้าง "
            f"{CONTROLS_FILENAME} ได้: {error}"
        )


def main():
    completed_names = load_processed_data()

    print(
        f"พบประวัติที่ทำสำเร็จแล้ว: "
        f"{len(completed_names)} รายการ"
    )
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")

    try:
        app = Application(
            backend="uia"
        ).connect(
            title_re=r".*Riposte.*",
            timeout=15,
        )

        main_window = app.window(
            title_re=r".*Riposte.*"
        )

        main_window.wait(
            "exists visible",
            timeout=15,
        )

        main_window.set_focus()

        # สร้างไฟล์ controls.txt ไว้ใช้ตรวจสอบ control จริง
        export_controls(main_window)

    except Exception:
        print(
            "เชื่อมต่อโปรแกรมไม่ได้ "
            "กรุณาตรวจสอบว่าเปิด Riposte อยู่"
        )
        traceback.print_exc()
        return

    print(f"กำลังเปิดไฟล์ข้อมูล {CSV_FILENAME}...")

    try:
        with open(
            CSV_FILENAME,
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:

            csv_reader = csv.DictReader(csv_file)
            validate_csv_headers(csv_reader.fieldnames)

            with open(
                LOG_FILENAME,
                mode="a",
                encoding="utf-8-sig",
            ) as log_file:

                for index, row in enumerate(
                    csv_reader,
                    start=1,
                ):
                    zip_code = clean_value(
                        row.get("PostalCode")
                    )

                    first_name = clean_value(
                        row.get("FirstName")
                    )

                    last_name = clean_value(
                        row.get("LastName")
                    )

                    unique_identifier = (
                        f"{first_name}|"
                        f"{last_name}|"
                        f"{zip_code}"
                    )

                    if (
                        not zip_code
                        or not first_name
                        or not last_name
                    ):
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            "PostalCode, FirstName "
                            "หรือ LastName ไม่ครบ ---"
                        )
                        continue

                    if unique_identifier in completed_names:
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            f"{first_name} {last_name} "
                            "(ทำไปแล้ว) ---"
                        )
                        continue

                    print(
                        f"--- กำลังทำรายการที่ {index}: "
                        f"{first_name} {last_name} ---"
                    )

                    try:
                        main_window.wait(
                            "exists visible enabled",
                            timeout=15,
                        )
                        main_window.set_focus()

                        # =========================
                        # หน้าเริ่มต้น
                        # =========================
                        wait_and_click(
                            main_window,
                            title_re=(
                                r".*รับฝากสิ่งของ.*"
                            ),
                        )
                        time.sleep(1)

                        wait_and_click(
                            main_window,
                            title_re=(
                                r".*กล่องสำเร็จรูป ข.*"
                            ),
                        )
                        time.sleep(1)

                        click_next(main_window)

                        wait_and_click(
                            main_window,
                            title_re=r"^ยืนยัน$",
                        )
                        time.sleep(1)

                        # =========================
                        # น้ำหนัก
                        # =========================
                        fill_edit(
                            main_window,
                            DEFAULT_WEIGHT,
                            title_re=r".*น้ำหนัก.*",
                        )

                        click_next(main_window)

                        # =========================
                        # รหัสไปรษณีย์
                        # =========================
                        fill_edit(
                            main_window,
                            zip_code,
                            title_re=(
                                r".*ระบุรหัสไปรษณีย์?.*"
                            ),
                        )

                        click_next(main_window)
                        time.sleep(2)

                        # =========================
                        # เลือก EMS
                        # =========================
                        print(
                            "[DEBUG] กำลังค้นหา "
                            "Image สำหรับ EMS"
                        )

                        ems_image = (
                            main_window.child_window(
                                control_type="Image",
                                found_index=0,
                            )
                        )

                        ems_image.wait(
                            "exists visible enabled",
                            timeout=15,
                        )

                        ems_image.wrapper_object().click_input()
                        time.sleep(1)

                        # กดถัดไป 3 รอบ
                        for round_number in range(1, 4):
                            print(
                                f"[DEBUG] กดถัดไป "
                                f"รอบที่ {round_number}/3"
                            )
                            click_next(main_window)

                        # =========================
                        # ค้นหาและเลือกที่อยู่
                        # =========================
                        fill_edit(
                            main_window,
                            DEFAULT_ADDRESS_SEARCH,
                            title_re=r"^ที่อยู่$",
                        )

                        time.sleep(2)
                        send_keys("{DOWN}")
                        send_keys("{ENTER}")
                        time.sleep(1)

                        click_next(main_window)

                        # =========================
                        # ข้อมูลผู้รับ
                        # =========================
                        fill_edit(
                            main_window,
                            first_name,
                            title_re=r"^ชื่อ$",
                        )

                        fill_edit(
                            main_window,
                            last_name,
                            title_re=r"^นามสกุล$",
                        )

                        fill_edit(
                            main_window,
                            PHONE_NUMBER,
                            title_re=(
                                r".*หมายเลขโทรศัพท์.*"
                            ),
                        )

                        # =========================
                        # สิ้นสุดกระบวนการ
                        # =========================
                        wait_and_click(
                            main_window,
                            title_re=r"^ไม่$",
                        )
                        time.sleep(2)

                        # ควรเพิ่มการตรวจสอบหน้า success
                        # ก่อนบันทึก log หากโปรแกรมมีข้อความ
                        # หรือ control ที่ยืนยันว่าพิมพ์สำเร็จ

                        log_file.write(
                            unique_identifier + "\n"
                        )
                        log_file.flush()

                        completed_names.add(
                            unique_identifier
                        )

                        print(
                            f"ทำรายการที่ {index} สำเร็จ "
                            "และบันทึกลง Log แล้ว"
                        )

                    except PywinautoTimeoutError:
                        print(
                            f"Timeout ที่รายการ {index}: "
                            f"{first_name} {last_name}"
                        )
                        traceback.print_exc()
                        recover_ui(main_window)

                    except Exception as error:
                        print(
                            f"เกิดข้อผิดพลาดที่รายการ "
                            f"{index}: "
                            f"{first_name} {last_name}"
                        )
                        print(
                            f"ชนิด Error: "
                            f"{type(error).__name__}"
                        )
                        print(
                            f"รายละเอียด: {error}"
                        )
                        traceback.print_exc()
                        recover_ui(main_window)

    except FileNotFoundError:
        print(
            f"ไม่พบไฟล์ {CSV_FILENAME} "
            "กรุณาตรวจสอบว่าไฟล์อยู่ใน "
            "โฟลเดอร์เดียวกับสคริปต์"
        )

    except PermissionError:
        print(
            f"ไม่สามารถเปิดไฟล์ {CSV_FILENAME} ได้ "
            "กรุณาปิดไฟล์ใน Excel แล้วลองใหม่"
        )

    except ValueError as error:
        print(
            f"โครงสร้าง CSV ไม่ถูกต้อง: {error}"
        )

    except Exception:
        print(
            "เกิดข้อผิดพลาดขณะอ่านหรือ "
            "ประมวลผลไฟล์ CSV"
        )
        traceback.print_exc()

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")


if __name__ == "__main__":
    main()