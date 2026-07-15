"""
เครื่องมือช่วย debug: dump control tree ของหน้าจอ Riposte ปัจจุบัน

วิธีใช้:
1. เปิดโปรแกรม Riposte ค้างไว้
2. เลื่อน/คลิกไปหน้าที่ต้องการดู (ด้วยมือ ปกติ) เช่น หน้าเลือกกล่อง,
   หน้ากรอกน้ำหนัก, หน้ากรอกที่อยู่ ฯลฯ
3. รันสคริปต์นี้ (python dump_screen.py หรือใส่ชื่อไฟล์ output เอง เช่น
   python dump_screen.py screen_box_select.txt)
4. จะได้ไฟล์ .txt ที่มี control tree ของหน้าจอ ณ ตอนนั้น -> ส่งไฟล์นั้นมาดูได้เลย

แนะนำ: ทำแบบนี้ทีละหน้า ไล่ตาม flow ทั้งหมด (เลือกกล่อง, ถัดไป, ยืนยัน,
น้ำหนัก, รหัสไปรษณีย์, เลือกบริการ EMS, ที่อยู่, ชื่อ-นามสกุล-เบอร์โทร)
แล้วส่งไฟล์ทั้งหมดมาในคราวเดียว จะได้แก้ auto_id ให้ครบทุกจุดในรอบเดียว
ไม่ต้องรอ fail ทีละจุด
"""

import sys
from pywinauto.application import Application


def main():
    output_filename = sys.argv[1] if len(sys.argv) > 1 else "screen_dump.txt"

    print("กำลังเชื่อมต่อโปรแกรม Riposte...")
    try:
        app = Application(backend="uia").connect(
            title_re=r".*Riposte.*", timeout=15
        )
        main_window = app.window(title_re=r".*Riposte.*")
        main_window.wait("exists visible", timeout=15)
        main_window.set_focus()
    except Exception as error:
        print(f"เชื่อมต่อไม่สำเร็จ: {error}")
        print("ตรวจสอบว่าเปิดโปรแกรม Riposte อยู่หรือไม่")
        return

    try:
        main_window.print_control_identifiers(filename=output_filename)
        print(f"บันทึก control tree ของหน้าจอปัจจุบันลง '{output_filename}' แล้ว")
        print("ส่งไฟล์นี้มาดูได้เลยครับ")
    except Exception as error:
        print(f"dump ไม่สำเร็จ: {error}")


if __name__ == "__main__":
    main()