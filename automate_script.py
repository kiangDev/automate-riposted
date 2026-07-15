import time
import csv
import os
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

def load_processed_data(log_filename="success_log.txt"):
    """ ฟังก์ชันสำหรับอ่านรายชื่อคนที่ทำสำเร็จแล้วขึ้นมาเก็บไว้ในความจำ """
    processed = set()
    if os.path.exists(log_filename):
        with open(log_filename, 'r', encoding='utf-8-sig') as f:
            for line in f:
                processed.add(line.strip())
    return processed

def main():
    # 1. โหลดประวัติเก่าขึ้นมาก่อนเริ่มงาน (ถ้าเพิ่งรันครั้งแรก มันจะคืนค่าว่างเปล่า)
    completed_names = load_processed_data("success_log.txt")
    print(f"พบประวัติที่ทำสำเร็จไปแล้ว: {len(completed_names)} รายการ")
    
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")
    app = Application(backend="uia").connect(title_re=".*Riposte.*")
    main_window = app.window(title_re=".*Riposte.*")
    
    print("กำลังอ่านไฟล์ data.csv...")
    with open('data.csv', mode='r', encoding='utf-8-sig') as file:
        csv_reader = csv.DictReader(file)
        
        # 2. เปิดไฟล์ Log เตรียมเขียนชื่อคนที่ทำสำเร็จเพิ่ม (ใช้โหมด 'a' คือ Append ต่อท้าย)
        with open("success_log.txt", "a", encoding='utf-8-sig') as log_file:
        
            for index, row in enumerate(csv_reader):
                
                # ดึงข้อมูลมาเตรียมไว้
                zip_code = row['PostalCode']
                f_name = row['FirstName']
                l_name = row['LastName']
                
                # ==== 3. ระบบเช็คประวัติ (ข้ามคนที่ทำไปแล้ว) ====
                # ในที่นี้ใช้ ชื่อ+นามสกุล เป็นตัวเช็ค (ถ้า CSV คุณมี OrderID ให้ใช้ OrderID จะชัวร์กว่าครับ)
                unique_identifier = f"{f_name} {l_name}"
                
                if unique_identifier in completed_names:
                    print(f"--- ข้ามรายการที่ {index + 1} : {unique_identifier} (ปริ้นใบเสร็จไปแล้ว) ---")
                    continue # สั่งให้ข้ามไปอ่านคนต่อไปใน CSV เลย
                
                print(f"--- กำลังทำรายการที่ {index + 1} : ผู้รับ {unique_identifier} ---")
                
                try:
                    # ================= เริ่มกระบวนการกรอก =================
                    main_window.child_window(title="รับฝากสิ่งของ").click_input() 
                    time.sleep(1)

                    main_window.child_window(title="กล่องสำเร็จรูป ข").click_input()
                    time.sleep(1)

                    main_window.child_window(title="ถัดไป", control_type="Button").click()
                    time.sleep(1)
                    main_window.child_window(title="ยืนยัน", control_type="Button").click()
                    time.sleep(1)

                    main_window.child_window(title="น้ำหนัก", control_type="Edit").type_keys("500")
                    main_window.child_window(title="ถัดไป", control_type="Button").click()
                    time.sleep(1)

                    main_window.child_window(title="ระบุรหัสไปรษณีย", control_type="Edit").type_keys(zip_code)
                    main_window.child_window(title="ถัดไป", control_type="Button").click()
                    time.sleep(2) 

                    main_window.child_window(control_type="Image", found_index=0).click_input()
                    
                    for _ in range(3):
                        main_window.child_window(title="ถัดไป", control_type="Button").click()
                        time.sleep(1)

                    main_window.child_window(title="ที่อยู่", control_type="Edit").type_keys("88")
                    time.sleep(2)
                    send_keys('{DOWN}')
                    send_keys('{ENTER}')
                    time.sleep(1)
                    main_window.child_window(title="ถัดไป", control_type="Button").click()
                    time.sleep(1)

                    main_window.child_window(title="ชื่อ", control_type="Edit").type_keys(f_name)
                    main_window.child_window(title="นามสกุล", control_type="Edit").type_keys(l_name)
                    main_window.child_window(title="หมายเลขโทรศัพท์", control_type="Edit").type_keys("0987654321")

                    main_window.child_window(title="ไม่", control_type="Button").click()
                    time.sleep(2)
                    
                    # ==== 4. อัปเดตสถานะความสำเร็จ ====
                    # ถ้าโค้ดรันมาถึงบรรทัดนี้ได้แปลว่า ไม่ค้าง ไม่พัง และทำทุกอย่างเสร็จสมบูรณ์
                    log_file.write(unique_identifier + "\n")
                    log_file.flush() # บังคับเซฟลง Harddisk ทันที! (กันไฟดับ)
                    
                    print(f"ทำรายการที่ {index + 1} สำเร็จ! (บันทึกสถานะแล้ว)")

                except Exception as e:
                    # ถ้ากระดาษหมด โปรแกรมค้าง โค้ดจะกระโดดมาที่นี่
                    # ซึ่งชื่อของคนๆ นี้ก็จะไม่ถูกเขียนลงไฟล์ success_log.txt
                    print(f"เกิดข้อผิดพลาดที่รายการ {index + 1}: {e}")
                    
                    # กด ESC เพื่อปิด Popup Error (ถ้ามี) หรือเคลียร์หน้าจอเตรียมพร้อมสำหรับรอบหน้า
                    send_keys('{ESC}')
                    time.sleep(1)

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")

if __name__ == "__main__":
    main()