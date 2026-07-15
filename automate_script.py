import csv
import os
import time
import traceback

from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto.timings import TimeoutError as PywinautoTimeoutError


CSV_FILENAME = "data.csv"
LOG_FILENAME = "success_log.txt"
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


def wait_and_click(window, **criteria):
    """รอให้ control พร้อม แล้วคลิก"""
    control = window.child_window(**criteria)
    control.wait("exists visible enabled ready", timeout=15)
    control.click_input()
    return control


def fill_edit(window, value, **criteria):
    """รอช่องกรอก ล้างข้อมูลเดิม แล้วกรอกค่าใหม่"""
    control = window.child_window(**criteria)
    control.wait("exists visible enabled ready", timeout=15)

    wrapper = control.wrapper_object()
    wrapper.click_input()

    try:
        # เหมาะกับ Edit control มาตรฐาน
        wrapper.set_edit_text(str(value))
    except Exception:
        # สำรองสำหรับช่องที่ไม่รองรับ set_edit_text
        send_keys("^a")
        send_keys("{BACKSPACE}")
        wrapper.type_keys(
            str(value),
            with_spaces=True,
            set_foreground=True,
        )

    return control


def click_next(window):
    """กดปุ่มถัดไป"""
    wait_and_click(
        window,
        title="ถัดไป",
        control_type="Button",
    )
    time.sleep(1)


def validate_csv_headers(fieldnames):
    required_headers = {"PostalCode", "FirstName", "LastName"}
    actual_headers = set(fieldnames or [])

    missing_headers = required_headers - actual_headers

    if missing_headers:
        missing_text = ", ".join(sorted(missing_headers))
        raise ValueError(
            f"CSV ขาด Header ที่จำเป็น: {missing_text}\n"
            f"Header ที่พบ: {fieldnames}"
        )


def recover_ui(main_window):
    """พยายามปิด popup และกลับสู่สถานะที่พร้อมทำรายการต่อ"""
    try:
        main_window.set_focus()
    except Exception:
        pass

    # กด ESC มากกว่าหนึ่งครั้ง เผื่อมี popup ซ้อน
    for _ in range(3):
        send_keys("{ESC}")
        time.sleep(0.5)


def main():
    completed_names = load_processed_data()

    print(f"พบประวัติที่ทำสำเร็จแล้ว: {len(completed_names)} รายการ")
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")

    try:
        app = Application(backend="uia").connect(
            title_re=r".*Riposte.*",
            timeout=15,
        )

        main_window = app.window(title_re=r".*Riposte.*")
        main_window.wait("exists visible ready", timeout=15)
        main_window.set_focus()

    except Exception:
        print("เชื่อมต่อโปรแกรมไม่ได้ กรุณาตรวจสอบว่าเปิด Riposte อยู่")
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

                for index, row in enumerate(csv_reader, start=1):
                    zip_code = clean_value(row.get("PostalCode"))
                    first_name = clean_value(row.get("FirstName"))
                    last_name = clean_value(row.get("LastName"))

                    # ชื่อเพียงอย่างเดียวอาจซ้ำกันได้ จึงใส่รหัสไปรษณีย์ด้วย
                    unique_identifier = (
                        f"{first_name}|{last_name}|{zip_code}"
                    )

                    if not zip_code or not first_name or not last_name:
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            "ข้อมูล PostalCode, FirstName หรือ LastName ไม่ครบ ---"
                        )
                        continue

                    if unique_identifier in completed_names:
                        print(
                            f"--- ข้ามรายการที่ {index}: "
                            f"{first_name} {last_name} (ทำไปแล้ว) ---"
                        )
                        continue

                    print(
                        f"--- กำลังทำรายการที่ {index}: "
                        f"{first_name} {last_name} ---"
                    )

                    try:
                        main_window.wait(
                            "exists visible enabled ready",
                            timeout=15,
                        )
                        main_window.set_focus()

                        # หน้าเริ่มต้น
                        wait_and_click(
                            main_window,
                            title="รับฝากสิ่งของ",
                            control_type="Custom",
                        )
                        time.sleep(1)

                        wait_and_click(
                            main_window,
                            title="กล่องสำเร็จรูป ข",
                        )
                        time.sleep(1)

                        click_next(main_window)

                        wait_and_click(
                            main_window,
                            title="ยืนยัน",
                            control_type="Button",
                        )
                        time.sleep(1)

                        # น้ำหนัก
                        fill_edit(
                            main_window,
                            DEFAULT_WEIGHT,
                            title="น้ำหนัก",
                            control_type="Edit",
                        )
                        click_next(main_window)

                        # รหัสไปรษณีย์
                        # ใช้ regular expression เพื่อรองรับทั้งแบบมีและไม่มี ์
                        fill_edit(
                            main_window,
                            zip_code,
                            title_re=r"ระบุรหัสไปรษณีย์?",
                            control_type="Edit",
                        )
                        click_next(main_window)
                        time.sleep(2)

                        # การใช้ found_index ยังมีความเสี่ยง
                        # ควรเปลี่ยนเป็น title หรือ auto_id ที่ตรวจจากโปรแกรมจริง
                        ems_image = main_window.child_window(
                            control_type="Image",
                            found_index=0,
                        )
                        ems_image.wait(
                            "exists visible enabled ready",
                            timeout=15,
                        )
                        ems_image.click_input()
                        time.sleep(1)

                        for _ in range(3):
                            click_next(main_window)

                        # ค้นหาที่อยู่
                        fill_edit(
                            main_window,
                            DEFAULT_ADDRESS_SEARCH,
                            title="ที่อยู่",
                            control_type="Edit",
                        )

                        time.sleep(2)
                        send_keys("{DOWN}")
                        send_keys("{ENTER}")
                        time.sleep(1)

                        click_next(main_window)

                        # ข้อมูลผู้รับ
                        fill_edit(
                            main_window,
                            first_name,
                            title="ชื่อ",
                            control_type="Edit",
                        )

                        fill_edit(
                            main_window,
                            last_name,
                            title="นามสกุล",
                            control_type="Edit",
                        )

                        fill_edit(
                            main_window,
                            PHONE_NUMBER,
                            title="หมายเลขโทรศัพท์",
                            control_type="Edit",
                        )

                        # ตรวจสอบว่าปุ่มนี้เป็นขั้นตอนที่ทำให้พิมพ์จริง
                        wait_and_click(
                            main_window,
                            title="ไม่",
                            control_type="Button",
                        )
                        time.sleep(2)

                        # ควรเพิ่มการตรวจสอบข้อความ/หน้าจอสำเร็จตรงนี้
                        # ก่อนบันทึกลง log

                        log_file.write(unique_identifier + "\n")
                        log_file.flush()

                        # ป้องกันข้อมูลซ้ำภายในการรันรอบปัจจุบัน
                        completed_names.add(unique_identifier)

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

                    except Exception:
                        print(
                            f"เกิดข้อผิดพลาดที่รายการ {index}: "
                            f"{first_name} {last_name}"
                        )
                        traceback.print_exc()
                        recover_ui(main_window)

    except FileNotFoundError:
        print(
            f"ไม่พบไฟล์ {CSV_FILENAME} "
            "กรุณาตรวจสอบว่าไฟล์อยู่ในโฟลเดอร์เดียวกับสคริปต์"
        )

    except PermissionError:
        print(
            f"ไม่สามารถเปิดไฟล์ {CSV_FILENAME} ได้ "
            "กรุณาปิดไฟล์ใน Excel แล้วลองใหม่"
        )

    except ValueError as error:
        print(f"โครงสร้าง CSV ไม่ถูกต้อง: {error}")

    except Exception:
        print("เกิดข้อผิดพลาดขณะอ่านหรือประมวลผลไฟล์ CSV")
        traceback.print_exc()

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")


if __name__ == "__main__":
    main()