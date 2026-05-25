/**
 * GeoSource Viewership Counter — Google Apps Script Web App
 *
 * 사용법:
 * 1. https://script.google.com 에서 새 프로젝트 생성
 * 2. 이 파일 내용 전체를 Code.gs 에 붙여넣기
 * 3. 새 Google Sheets 문서 생성 → 그 URL을 SPREADSHEET_ID 자리에 ID만 채우거나,
 *    이 스크립트를 해당 Sheets에서 "확장 프로그램 → Apps Script"로 열어 작성하면 자동 연결됨.
 * 4. 배포 → 새 배포 → 유형 "웹 앱"
 *    - 실행 계정: 본인
 *    - 액세스 권한: "모든 사용자" (익명 포함)
 *    - 배포 후 받는 Web App URL을 index.html 의 VIEWERSHIP_URL 상수에 넣기
 * 5. 시트 이름은 자동으로 'viewership' 생성되며 컬럼은 [date, count] 두 개.
 *
 * 호출 규약:
 *   GET ?action=read   → 현재 Today/Total 만 반환 (카운트 증가 X)
 *   GET ?action=count  → 오늘 행 +1 후 Today/Total 반환
 *
 * 응답: { today: <number>, total: <number> }
 */

const SHEET_NAME = 'viewership';
const TIMEZONE = 'Asia/Seoul';

function doGet(e) {
  const action = ((e && e.parameter && e.parameter.action) || 'read').toLowerCase();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(['date', 'count']);
  }

  const today = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);

  try {
    const data = sheet.getDataRange().getValues();
    let todayRow = -1;
    let todayCount = 0;
    let total = 0;

    for (let i = 1; i < data.length; i++) {
      const d = data[i][0];
      const dStr = (d instanceof Date)
        ? Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd')
        : String(d);
      const c = Number(data[i][1]) || 0;
      total += c;
      if (dStr === today) {
        todayRow = i + 1;
        todayCount = c;
      }
    }

    if (action === 'count') {
      todayCount += 1;
      total += 1;
      if (todayRow > 0) {
        sheet.getRange(todayRow, 2).setValue(todayCount);
      } else {
        sheet.appendRow([today, 1]);
      }
    }

    return ContentService
      .createTextOutput(JSON.stringify({ today: todayCount, total: total }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}
