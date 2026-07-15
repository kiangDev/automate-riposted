import csv
import time
from pywinauto.application import Application

# 1. ฟังก์ชันสำหรับจัดการโปรแกรม Riposte 1 รายการ (1 แถวข้อมูล)
def process_single_record(main_window, record_data):
    try:
        # สมมติว่า record_data เป็น Dictionary ที่มีคีย์ 'ID', 'Name', 'Amount'
        
        # ค้นหาช่องกรอกข้อมูลและพิมพ์
        # (คุณต้องไปใช้ Inspect.exe เพื่อหา auto_id หรือ title ของช่องเหล่านี้ใน Riposte อีกที)
        main_window.child_window(auto_id="Field_ID").type_keys(record_data['ID'])
        main_window.child_window(auto_id="รับฝากสิิ่งของ").type_keys(record_data['Name'])
        
        # คลิกปุ่ม Save
        main_window.child_window(title="Save", control_type="Button").click()
        
        # รอโปรแกรมโหลด (ถ้ามีหน้าต่าง popup ว่าบันทึกสำเร็จ)
        # time.sleep(1) หรือใช้ Waiter ของ pywinauto
        
        # กดปุ่ม New เพื่อเตรียมกรอกข้อมูลรายการต่อไป
        main_window.child_window(title="New Record", control_type="Button").click()
        
        return True, "Success"
        
    except Exception as e:
        # ถ้าหาปุ่มไม่เจอ หรือโปรแกรมค้าง จะเด้งมาที่นี่
        return False, str(e)

def main():
    # 2. เชื่อมต่อกับโปรแกรม Riposte ที่เปิดอยู่แล้ว
    # (หรือใช้ .start() ถ้าต้องการให้ Python เปิดโปรแกรมให้ใหม่)
    try:
        app = Application(backend="uia").connect(title_re=".*Riposte.*")
        main_window = app.window(title_re=".*Riposte.*")
        # รอให้หน้าต่างพร้อม
        main_window.wait('ready', timeout=10)
    except Exception as e:
        print("หาหน้าต่างโปรแกรม Riposte ไม่เจอ กรุณาเปิดโปรแกรมเตรียมไว้ก่อน")
        return

    # 3. เตรียมไฟล์สำหรับเก็บ Log ว่าอันไหนทำผ่าน/ไม่ผ่าน
    success_log = open('success_log.csv', 'a', encoding='utf-8')
    error_log = open('error_log.csv', 'a', encoding='utf-8')

    # 4. อ่านข้อมูล 3,000 รายการ และวนลูป
    with open('data.csv', mode='r', encoding='utf-8-sig') as file:
        csv_reader = csv.DictReader(file)
        
        for index, row in enumerate(csv_reader):
            print(f"กำลังประมวลผลรายการที่ {index + 1} (ID: {row.get('ID', 'N/A')})...")
            
            # ส่งข้อมูลไปกรอกหน้าจอ
            is_success, msg = process_single_record(main_window, row)
            
            if is_success:
                print(" -> สำเร็จ")
                success_log.write(f"{row.get('ID')},SUCCESS\n")
            else:
                print(f" -> ล้มเหลว: {msg}")
                error_log.write(f"{row.get('ID')},FAILED,{msg}\n")
                
                # หากโปรแกรมค้าง อาจจะต้องใส่โค้ดสำหรับกู้คืนหน้าจอ (Recovery) ตรงนี้
                # เช่น การกดปุ่ม ESC เพื่อปิด Popup ที่ค้างอยู่
            
            # หน่วงเวลาเล็กน้อยกันโปรแกรมรับไม่ทัน (ถ้าจำเป็น)
            time.sleep(0.5)

    success_log.close()
    error_log.close()
    print("เสร็จสิ้นกระบวนการทั้งหมด!")

if __name__ == "__main__":
    main()