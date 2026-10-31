import type { FieldError } from "./api";

// The API answers in short English; these are the messages a person can run into when editing a preset.
const EXACT: Record<string, string> = {
  "file not found": "ไม่พบไฟล์นี้ในเครื่อง",
  "path not found": "ไม่พบไฟล์หรือโฟลเดอร์นี้ในเครื่อง",
  "must be an absolute path": "ต้องเป็น path เต็ม เช่น C:\\Program Files\\...",
  "must be an .exe file": "ต้องเป็นไฟล์ .exe",
  "only http:// and https:// URLs are allowed": "ใช้ได้เฉพาะลิงก์ที่ขึ้นต้นด้วย http:// หรือ https://",
  "a URL must not contain spaces": "ลิงก์ต้องไม่มีช่องว่าง",
  "must start with a scheme such as discord:": "ต้องขึ้นต้นด้วยชื่อแอป เช่น discord:",
  "every phrase needs at least one letter or digit": "วลีต้องมีตัวอักษรหรือตัวเลขอย่างน้อย 1 ตัว",
  "a preset with this name already exists": "มี preset ชื่อนี้อยู่แล้ว",
  "at least one preset must remain": "ต้องเหลือ preset อย่างน้อย 1 อัน",
  "Field required": "ต้องกรอก",
};

export function thaiError(message: string): string {
  if (EXACT[message]) return EXACT[message];
  const used = /^'(.*)' is already used by preset '(.*)'$/.exec(message);
  if (used) return `วลี "${used[1]}" ถูกใช้ใน preset "${used[2]}" แล้ว ใช้ซ้ำกันไม่ได้`;
  const scheme = /^the '(.*)' scheme is not allowed$/.exec(message);
  if (scheme) return `ไม่อนุญาตลิงก์ชนิด ${scheme[1]} (ไม่ปลอดภัย)`;
  const longer = /at most (\d+) (character|item)/.exec(message);
  if (longer) return `ยาวเกินไป (สูงสุด ${longer[1]})`;
  if (/at least 1 (character|item)/.test(message)) return "ต้องกรอกอย่างน้อย 1 รายการ";
  const range = /greater than or equal to (\d+)|less than or equal to (\d+)/.exec(message);
  if (range) return `ค่าต้องอยู่ระหว่าง 0 ถึง 30`;
  return message;
}

const FIELD_NAME: Record<string, string> = {
  name: "ชื่อ",
  phrases: "วลี",
  reply: "คำตอบ",
  actions: "ขั้นตอน",
  path: "ไฟล์",
  target: "เป้าหมาย",
  args: "อาร์กิวเมนต์",
  urls: "ลิงก์",
  seconds: "วินาที",
  period: "ช่วงเวลา",
};

/** "actions.1.path" -> "ขั้นตอนที่ 2 · ไฟล์" */
export function describeField(field: string): string {
  const step = /^actions\.(\d+)(?:\.(\w+))?/.exec(field);
  if (step) {
    const where = `ขั้นตอนที่ ${Number(step[1]) + 1}`;
    return step[2] ? `${where} · ${FIELD_NAME[step[2]] ?? step[2]}` : where;
  }
  return FIELD_NAME[field] ?? field;
}

/** Messages for one field path, in Thai. */
export function messagesFor(errors: FieldError[], field: string): string[] {
  return errors.filter((e) => e.field === field).map((e) => thaiError(e.message));
}
