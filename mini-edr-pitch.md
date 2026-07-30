# mini EDR บน macOS ที่ระดับ system call

**ข้อเสนอโปรเจกต์จบ / ฝึกงาน** — เขียนด้วย Zig + arm64 assembly, โฟกัสที่ file & persistence telemetry
ระยะเวลา 24 สัปดาห์ · ผู้เสนอ: kiang

---

## 1. ปัญหา

องค์กรไทยเริ่มใช้ Mac เป็นเครื่องทำงานมากขึ้น แต่ความเข้าใจเรื่อง endpoint security บน macOS
ยังตามหลัง Windows อยู่หลายก้าว ปัญหาที่เห็นชัดสามข้อ:

**หนึ่ง — EDR บน macOS เป็นกล่องดำ** ทีม security ส่วนใหญ่ซื้อ EDR มาใช้โดยไม่รู้ว่ามันเห็นอะไรและ
ไม่เห็นอะไร เมื่อเกิด incident จริงจึงตอบไม่ได้ว่า "ที่ log ไม่มี event นี้ เพราะไม่มีการโจมตี
หรือเพราะ sensor มองไม่เห็น"

**สอง — เอกสารและงานสอนเรื่อง kernel ของ macOS มีน้อย** ตำรา OS ส่วนใหญ่สอน Linux ทั้งที่ XNU
มีสถาปัตยกรรมต่างออกไปมาก (Mach + BSD, MACF, SIP, kext ที่ถูกยกเลิก) นักศึกษาที่อยากเข้าใจ
kernel ของเครื่องที่ตัวเองใช้อยู่ทุกวันแทบไม่มีทางเริ่ม

**สาม — ช่องว่างการมองเห็นในชั้น filesystem ของ APFS** งานวิจัยเรื่อง EDR evasion บน macOS
ยังบางมาก โดยเฉพาะ syscall เฉพาะทางของ APFS เช่น `clonefile(2)`, `fclonefileat(2)`,
`renameatx_np(2)` ที่ใช้คัดลอกและสลับไฟล์ได้โดยไม่ผ่านเส้นทาง `open`/`write` แบบเดิม
เครื่องมือ monitoring แต่ละชั้นเห็นมันไม่เท่ากัน แต่ยังไม่มีใครวัดออกมาเป็นตัวเลข

## 2. ทำไมผมอยากทำ — ความรู้ที่ต้องการจากโปรเจกต์นี้

ผมไม่ได้ต้องการทำ "อีกหนึ่ง security tool" ผมต้องการเข้าใจ **เส้นทางที่คำสั่งหนึ่งคำสั่งเดินจาก
โปรแกรมของผมลงไปถึง kernel แล้วกลับขึ้นมา** อย่างละเอียดจริง ๆ ไม่ใช่ระดับที่อ่านสไลด์แล้วจำได้

การเขียน EDR บังคับให้ผมต้องรู้สี่เรื่องนี้แบบไม่มีทางเลี่ยง:

1. **syscall ABI ระดับ instruction** — บน arm64 การเรียก syscall คือ `svc #0x80` โดยหมายเลข
   syscall อยู่ใน `x16` (ค่าบวก = BSD syscall, ค่าลบ = Mach trap) และ argument อยู่ใน `x0`–`x7`
   ถ้าผมเขียน assembly ยิง syscall เองได้ ผมก็เข้าใจ boundary นี้จริง
2. **เส้นทางภายใน XNU** — `sysent` table ที่ถูก generate จาก `bsd/kern/syscalls.master`,
   ชั้น VFS ใน `bsd/vfs/`, และจุดที่ security policy ถูกเรียก
3. **MACF (TrustedBSD MAC Framework)** — จุดที่ Sandbox, AMFI และ EndpointSecurity เสียบตัวเอง
   เข้าไปในเส้นทาง syscall นี่คือหัวใจที่ผมอยากเข้าใจที่สุด เพราะมันอธิบายว่า *ทำไม* EDR บน macOS
   เห็นบางอย่างและไม่เห็นบางอย่าง
4. **ข้อจำกัดเชิงสถาปัตยกรรมของแพลตฟอร์มปิด** — SIP, code signing, entitlement, การตาย
   ของ kext ล้วนเป็นการตัดสินใจเชิงออกแบบที่มีเหตุผล การชนกับข้อจำกัดพวกนี้ด้วยมือตัวเอง
   สอนเรื่อง OS security design ได้มากกว่าการอ่าน

สิ่งที่ผมจะได้ติดตัวไปหลังจบ: อ่าน kernel source ของระบบปิดได้, เขียนโค้ดที่คุยกับ kernel API
ระดับ C ได้, ออกแบบการทดลองเพื่อวัดขอบเขตความสามารถของเครื่องมือได้ — ทักษะชุดนี้ใช้ได้ทั้งสาย
security engineering และ systems programming

## 3. คำถามวิจัย

> ชั้น monitoring ที่ใช้ได้จริงบน macOS สมัยใหม่ — FSEvents, kqueue/vnode และ EndpointSecurity —
> เห็น file operation ครบต่างกันแค่ไหน และมี syscall ใดที่หลุดจากการมองเห็นของแต่ละชั้น?

คำถามนี้ตอบได้ด้วยการวัด ไม่ใช่ด้วยความเห็น และคำตอบมีประโยชน์ต่อคนอื่นจริง

## 4. สิ่งที่จะสร้าง

| ส่วน | รายละเอียด |
|---|---|
| **Sensor** | EndpointSecurity client เขียนด้วย Zig (ผ่าน `@cImport` เข้า header ภาษา C ตรง ๆ) subscribe event ตระกูลไฟล์: `ES_EVENT_TYPE_NOTIFY_CREATE`, `_WRITE`, `_RENAME`, `_UNLINK`, `_CLONE`, `_EXEC` |
| **Persistence watcher** | เฝ้าจุดที่มัลแวร์ macOS ใช้ฝังตัวจริง — `LaunchAgents`/`LaunchDaemons` plist, login items, `~/Library/Preferences` (macOS ไม่มี registry ของเทียบเท่าคือชั้นนี้) |
| **Rule engine** | กฎแบบประกาศ (declarative) เทียบเคียงแนวคิด Sigma พร้อม process ancestry เพื่อลด false positive |
| **asm coverage harness** | โปรแกรม arm64 assembly ที่ยิง raw syscall ข้าม libc เพื่อทดสอบว่าแต่ละชั้น sensor ยังเห็นหรือไม่ รวม syscall เฉพาะของ APFS |
| **ผลการวัด** | ตาราง coverage matrix: syscall × ชั้น sensor × เห็น/ไม่เห็น/เห็นบางส่วน |

**ยังไม่ทำในรอบนี้ (ตัดออกอย่างตั้งใจ):** network telemetry, การบล็อกแบบ AUTH event,
central server หลายเครื่อง, การแจกจ่ายผ่าน MDM — เพื่อให้ 24 สัปดาห์ทำเสร็จได้จริงและลึกพอ

## 5. ทำไม Zig และทำไม assembly

**Zig** — เข้า C API ได้โดยไม่ต้องเขียน binding, ควบคุมการจัดสรรหน่วยความจำได้ชัดเจน (สำคัญมาก
เพราะ ES handler ที่ทำงานช้าเกิน deadline จะถูก kernel ฆ่า client ทิ้ง), และไม่มี hidden control flow
ให้เดา — เหมาะกับโค้ดที่ต้องอธิบายพฤติกรรมได้ทุกบรรทัด

**Assembly** — ไม่ได้ใส่มาเพื่อความเท่ แต่เพราะการทดสอบ coverage ต้องยิง syscall ที่ libc
ไม่มี wrapper ให้ และต้องมั่นใจว่าไม่มีชั้นไหนมาแทรกกลาง นี่คือส่วนที่เปลี่ยนโปรเจกต์นี้จาก
"เครื่องมือ" ให้เป็น "การวัดผล"

## 6. แผน 24 สัปดาห์

| ช่วง | งาน |
|---|---|
| สัปดาห์ 1–4 | อ่าน XNU source ไล่เส้นทาง `open(2)` ตั้งแต่ `svc` ถึง MACF hook เขียนสรุปเป็นเอกสาร |
| สัปดาห์ 5–8 | ตั้ง dev environment (SIP/AMFI, entitlement), ES client ตัวแรกใน Zig ที่ปรินต์ event ได้ |
| สัปดาห์ 9–12 | asm harness + ทดลองวัดชั้น FSEvents / kqueue / ES ครั้งแรก |
| สัปดาห์ 13–16 | Rule engine + persistence watcher |
| สัปดาห์ 17–20 | รวบรวม coverage matrix, ทำซ้ำให้ผลนิ่ง, จำลอง ransomware behaviour เพื่อทดสอบ |
| สัปดาห์ 21–24 | เขียนรายงาน, เตรียม demo, เผยแพร่โค้ดและผลการวัด |

## 7. ความเสี่ยงและแผนสำรอง

| ความเสี่ยง | แผนสำรอง |
|---|---|
| ขอ entitlement `com.apple.developer.endpoint-security.client` จาก Apple ไม่ผ่าน | ใช้เครื่อง dev ที่ปิด SIP + `amfi_get_out_of_my_way=1` ซึ่งเป็นวิธีมาตรฐานของงานวิจัยด้านนี้ |
| ES client รันไม่ได้เลยด้วยเหตุสุดวิสัย | เปลี่ยนไปดึง event ผ่าน `/usr/bin/eslogger` ของ Apple แทน ได้ข้อมูลชุดเดียวกันแต่ไม่ต้องมี entitlement |
| Zig ยังไม่ stable ที่ API ระดับนี้ | ส่วนที่ติดกับ ES API เขียนเป็น C แล้วให้ Zig เรียก |

## 8. ผลลัพธ์ที่ส่งมอบ

1. Source code ของ mini EDR (เปิดเป็น open source)
2. เอกสารอธิบายเส้นทาง syscall → VFS → MACF → EndpointSecurity บน macOS ภาษาไทย
3. Coverage matrix พร้อมวิธีทำซ้ำการทดลอง
4. รายงานและ demo ที่รัน detection ได้จริงบนเครื่องทดสอบ

---

*หมายเหตุด้านจริยธรรม: โปรเจกต์นี้เป็นงานฝ่ายป้องกัน ตัวอย่างพฤติกรรมที่ใช้ทดสอบเป็น
โปรแกรมจำลองที่เขียนขึ้นเองและรันเฉพาะใน VM ที่แยกออกจากเครือข่าย ไม่มีการสร้างหรือเผยแพร่มัลแวร์*
