import time
import csv
from pywinauto.application import Application
from pywinauto.keyboard import send_keys

def main():
    # 1. เชื่อมต่อกับโปรแกรม Riposte (ต้องเปิดโปรแกรมทิ้งไว้ก่อน)
    print("กำลังเชื่อมต่อโปรแกรม Riposte...")
    app = Application(backend="uia").connect(title_re=".*Riposte.*")
    main_window = app.window(title_re=".*Riposte.*")
    
    # 2. เปิดไฟล์ CSV ขึ้นมาอ่าน
    print("กำลังอ่านไฟล์ data.csv...")
    with open('data.csv', mode='r', encoding='utf-8-sig') as file:
        
        # DictReader จะอ่านไฟล์โดยใช้บรรทัดแรก (Header) เป็น Key (ตัวแปร)
        csv_reader = csv.DictReader(file)
        
        # 3. วนลูปอ่านข้อมูลทีละแถว (1 แถว = ผู้รับ 1 คน)
        for index, row in enumerate(csv_reader):
            print(f"--- กำลังทำรายการที่ {index + 1} : ผู้รับ {row['FirstName']} ---")
            
            try:
                # ดึงข้อมูลจากไฟล์ CSV มาเก็บในตัวแปร
                zip_code = row['PostalCode']
                f_name = row['FirstName']
                l_name = row['LastName']
                
                # ================= เริ่มกระบวนการกรอก =================
                
                # 1. รับฝากสิ่งของ
                main_window.child_window(title="รับฝากสิ่งของ").click_input() 
                time.sleep(1)

                # 2. กล่องสำเร็จรูป ข
                main_window.child_window(title="กล่องสำเร็จรูป ข").click_input()
                time.sleep(1)

                # 3. ถัดไป & ยืนยัน
                main_window.child_window(title="ถัดไป", control_type="Button").click()
                time.sleep(1)
                main_window.child_window(title="ยืนยัน", control_type="Button").click()
                time.sleep(1)

                # 4. กรอกน้ำหนัก
                main_window.child_window(title="น้ำหนัก", control_type="Edit").type_keys("500")
                main_window.child_window(title="ถัดไป", control_type="Button").click()
                time.sleep(1)

                # 5. กรอกรหัสไปรษณีย์ (ดึงมาจากตัวแปร zip_code ที่อ่านจาก CSV)
                main_window.child_window(title="ระบุรหัสไปรษณีย", control_type="Edit").type_keys(zip_code)
                main_window.child_window(title="ถัดไป", control_type="Button").click()
                time.sleep(2) # รอโหลด

                # 6. เลือกบริการ EMS
                main_window.child_window(control_type="Image", found_index=0).click_input()
                
                # 7. กดถัดไป 3 รอบ
                for _ in range(3):
                    main_window.child_window(title="ถัดไป", control_type="Button").click()
                    time.sleep(1)

                # 8. ที่อยู่ (พิมพ์ 88, เลื่อนลง 1 ที, กด Enter)
                main_window.child_window(title="ที่อยู่", control_type="Edit").type_keys("88")
                time.sleep(2)
                send_keys('{DOWN}')
                send_keys('{ENTER}')
                time.sleep(1)
                main_window.child_window(title="ถัดไป", control_type="Button").click()
                time.sleep(1)

                # 9. กรอกชื่อ นามสกุล (ดึงมาจากตัวแปร f_name, l_name ที่อ่านจาก CSV)
                main_window.child_window(title="ชื่อ", control_type="Edit").type_keys(f_name)
                main_window.child_window(title="นามสกุล", control_type="Edit").type_keys(l_name)
                
                # 10. เบอร์โทร (Fix ไว้ตามที่คุณแจ้ง)
                main_window.child_window(title="หมายเลขโทรศัพท์", control_type="Edit").type_keys("0987654321")

                # จบกระบวนการ กด "ไม่" เพื่อกลับไปหน้าแรก (เตรียมพร้อมสำหรับลูปรอบต่อไป)
                main_window.child_window(title="ไม่", control_type="Button").click()
                time.sleep(2)
                
                print(f"ทำรายการที่ {index + 1} สำเร็จ!")

            except Exception as e:
                # ถ้าแถวไหน Error ให้โปรแกรมไม่พัง แต่ข้ามไปทำแถวถัดไปแทน
                print(f"เกิดข้อผิดพลาดที่รายการ {index + 1}: {e}")
                # ควรกด ESC หรือกลับหน้าหลัก เพื่อรีเซ็ตหน้าจอให้พร้อมสำหรับคิวถัดไป
                send_keys('{ESC}')
                time.sleep(1)

    print("เสร็จสิ้นการทำงานทั้งหมดแล้ว!")

if __name__ == "__main__":
    main()