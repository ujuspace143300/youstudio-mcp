// wrangler rules(Text) 로 import 하는 .md 의 타입 — 내용은 문자열
declare module "*.md" {
  const text: string;
  export default text;
}
