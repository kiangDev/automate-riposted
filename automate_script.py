import time
import csv
import os
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

def load_processed_data(log_filename="success_log.txt"):
    """ ฟังก์ชันสำหรับอ่านรายชื่อคนที่ปริ้นสำเร็จแล้วขึ้นมาจำไว้ เพื่อใช้ข้ามคิว """
    processed = set()
    if os.path.exists(log_filename):
        with open(log_filename, 'r', encoding='utf-8-sig') as f:
            for line in f:
                processed.add(line.strip())
    return processed

def main():
    # 1. โหลดประวัติเก่าขึ้นมาก่อนเริ่มงาน
    completed_names = load_processed_data("success_log.txt")
    print(f"พบประวัติที่ทำสำเร็จไปแล้ว: {len(completed_names)} รายการ")
    
    # 2. เชื่อมต่อโปรแกรม (เปิดโปรแกรมไปรษณีย์เตรียมไว้ที่หน้าแรก)
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")
    try:
        app = Application(backend="uia").connect(title_re=".*Riposte.*")
        main_window = app.window(title_re=".*Riposte.*")
    except Exception as e:
        print("เชื่อมต่อโปรแกรมไม่ได้ กรุณาเช็คว่าเปิดโปรแกรม Riposte ไว้หรือยัง")
        return
    
    print("กำลังเปิดไฟล์ข้อมูล data.csv...")
    try:
        # 3. เปิดไฟล์ CSV ขึ้นมาอ่าน (อย่าลืมเปลี่ยนชื่อไฟล์ให้ตรงกับของคุณ)
        with open('data.csv', mode='r', encoding='utf-8-sig') as file:
            csv_reader = csv.DictReader(file)
            
            # 4. เปิดไฟล์ Log เตรียมเขียนชื่อคนที่ทำสำเร็จ
            with open("success_log.txt", "a", encoding='utf-8-sig') as log_file:
            
                for index, row in enumerate(csv_reader):
                    
                    # ดึงข้อมูลจาก CSV ลงตัวแปร (แก้ชื่อ Key ในวงเล็บให้ตรงกับ Header CSV ของคุณ)
                    zip_code = row['PostalCode']
                    f_name = row['FirstName']
                    l_name = row['LastName']
                    
                    # ใช้ชื่อและนามสกุลเป็นตัวเช็คประวัติ
                    unique_identifier = f"{f_name} {l_name}"
                    
                    # ตรวจสอบว่าเคยทำรายการนี้ผ่านไปแล้วหรือยัง
                    if unique_identifier in completed_names:
                        print(f"--- ข้ามรายการที่ {index + 1} : {unique_identifier} (ปริ้นไปแล้ว) ---")
                        continue 
                    
                    print(f"--- กำลังทำรายการที่ {index + 1} : {unique_identifier} ---")
                    
                    try:
                        # ================= กระบวนการคลิกและพิมพ์ (UI) =================
                        main_window.wait('ready',timeout=10)

                        
                        main_window.child_window(title="รับฝากสิ่งของ",control_type="Custom").click_input() 
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
                        time.sleep(2) # รอโหลดหน้าบริการ

                        # เลือก EMS (อันซ้ายสุด)
                        main_window.child_window(control_type="Image", found_index=0).click_input()
                        
                        # กดถัดไป 3 รอบ
                        for _ in range(3):
                            main_window.child_window(title="ถัดไป", control_type="Button").click()
                            time.sleep(1)

                        # ค้นหาและเลือกที่อยู่
                        main_window.child_window(title="ที่อยู่", control_type="Edit").type_keys("88")
                        time.sleep(2)
                        send_keys('{DOWN}')
                        send_keys('{ENTER}')
                        time.sleep(1)
                        main_window.child_window(title="ถัดไป", control_type="Button").click()
                        time.sleep(1)

                        # ข้อมูลผู้รับ
                        main_window.child_window(title="ชื่อ", control_type="Edit").type_keys(f_name)
                        main_window.child_window(title="นามสกุล", control_type="Edit").type_keys(l_name)
                        main_window.child_window(title="หมายเลขโทรศัพท์", control_type="Edit").type_keys("0987654321")

                        # สิ้นสุดกระบวนการ (กด ไม่ / ออกจากหน้า)
                        main_window.child_window(title="ไม่", control_type="Button").click()
                        time.sleep(2)
                        
                        # ================= เซฟประวัติความสำเร็จ =================
                        # ถ้าโค้ดรันมาถึงตรงนี้ แสดงว่าปริ้นสำเร็จ ไม่มีแจ้งเตือน Error ใดๆ
                        log_file.write(unique_identifier + "\n")
                        log_file.flush() # เซฟลงฮาร์ดดิสก์ทันที
                        
                        print(f"ทำรายการที่ {index + 1} สำเร็จ! บันทึกลง Log แล้ว")

                    except Exception as e:
                        # กรณีเกิด Error (เช่น กระดาษหมด, หาปุ่มไม่เจอ, โปรแกรมค้าง)
                        print(f"เกิดข้อผิดพลาดที่รายการ {index + 1}: {e}")
                        
                        # พยายามกดปุ่ม ESC เพื่อเคลียร์ Popup หรือหน้าต่างที่ค้างอยู่
                        send_keys('{ESC}')
                        time.sleep(1)
                        # กลับไปเริ่มลูปใหม่ (ชื่อคนนี้จะไม่ถูกบันทึกลง Log รันรอบหน้าจะถูกทำใหม่)

    except FileNotFoundError:
        print("ไม่พบไฟล์ data.csv กรุณาตรวจสอบว่ามีไฟล์อยู่ในโฟลเดอร์เดียวกันหรือไม่")

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")

if __name__ == "__main__":
    main()