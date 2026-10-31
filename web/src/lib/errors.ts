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
  "this key name is not recognized": "ระบบไม่รู้จักปุ่มนี้",
  "use one key or a combo like ctrl+alt+j": "ใช้ปุ่มเดียว หรือคอมโบ เช่น ctrl+alt+j",
  "in a combo, every key before the last must be ctrl, alt, shift or windows": "ในคอมโบ ปุ่มก่อนปุ่มสุดท้ายต้องเป็น ctrl, alt, shift หรือ windows",
  "hotkey must be text": "ปุ่มลัดต้องเป็นข้อความ",
};

export function thaiError(message: string): string {
  if (EXACT[message]) return EXACT[message];
  const used = /^'(.*)' is already used by preset '(.*)'$/.exec(message);
  if (used) return `วลี "${used[1]}" ถูกใช้ใน preset "${used[2]}" แล้ว ใช้ซ้ำกันไม่ได้`;
  const contains = /^'(.*)' contains the phrase '(.*)' of preset '(.*)': Jarvis could not tell which one you mean$/.exec(message);
  if (contains) return `วลี "${contains[1]}" มีวลี "${contains[2]}" ของ preset "${contains[3]}" ซ้อนอยู่ข้างใน Jarvis แยกไม่ออกว่าหมายถึงอันไหน จึงจับคู่ไม่ได้`;
  const partOf = /^'(.*)' is part of the phrase '(.*)' of preset '(.*)': Jarvis could not tell which one you mean$/.exec(message);
  if (partOf) return `วลี "${partOf[1]}" เป็นส่วนหนึ่งของวลี "${partOf[2]}" ใน preset "${partOf[3]}" Jarvis แยกไม่ออกว่าหมายถึงอันไหน จึงจับคู่ไม่ได้`;
  const tooClose = /^'(.*)' is too close to other phrases to be recognised$/.exec(message);
  if (tooClose) return `วลี "${tooClose[1]}" ใกล้เคียงกับวลีอื่นมาก Jarvis จะจับคู่ไม่ได้`;
  const breaks = /^saving this would stop Jarvis recognising '(.*)' of preset '(.*)'$/.exec(message);
  if (breaks) return `ถ้าบันทึกแบบนี้ คำสั่ง "${breaks[1]}" ของ preset "${breaks[2]}" จะใช้ไม่ได้อีก`;
  const typing = /^'(.*)' is a typing key: use it with a modifier, e\.g\. (.*)$/.exec(message);
  if (typing) return `"${typing[1]}" เป็นปุ่มพิมพ์ ใช้เดี่ยว ๆ ไม่ได้ (จะพิมพ์ไม่ออก) ลองใช้คู่กับ Ctrl/Alt เช่น ${typing[2]}`;
  if (message.startsWith("a combo must end with a normal key")) return "คอมโบต้องลงท้ายด้วยปุ่มปกติ เช่น ctrl+alt+j";
  const scheme = /^the '(.*)' scheme is not allowed$/.exec(message);
  if (scheme) return `ไม่อนุญาตลิงก์ชนิด ${scheme[1]} (ไม่ปลอดภัย)`;
  const longer = /at most (\d+) (character|item)/.exec(message);
  if (longer) return `ยาวเกินไป (สูงสุด ${longer[1]})`;
  if (/at least 1 (character|item)/.test(message)) return "ต้องกรอกอย่างน้อย 1 รายการ";
  const low = /greater than or equal to ([\d.]+)/.exec(message);
  if (low) return `ค่าต้องไม่น้อยกว่า ${low[1]}`;
  const high = /less than or equal to ([\d.]+)/.exec(message);
  if (high) return `ค่าต้องไม่เกิน ${high[1]}`;
  if (/valid integer/.test(message)) return "ต้องเป็นจำนวนเต็ม";
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
  hotkey: "ปุ่มลัด",
  silence_ms: "เวลาเงียบก่อนหยุด",
  max_seconds: "ฟังนานสุด",
  match_threshold: "ความมั่นใจขั้นต่ำ",
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
