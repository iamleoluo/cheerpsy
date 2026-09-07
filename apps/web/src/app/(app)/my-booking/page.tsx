/**
 * 心理師端「預約作業」。GET /cases、/institution/eligible-plans、
 * POST /appointments 在後端對 role=therapist 都已自動限定為本人個案
 * （見 routers/cases.py、routers/appointments.py 的角色過濾與 403 檢查），
 * 所以行政端／心理師端可以直接共用同一份表單元件，不用另外重寫一份。
 */
export { default } from "../booking/page";
