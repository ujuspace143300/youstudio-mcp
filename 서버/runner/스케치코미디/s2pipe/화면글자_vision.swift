// 화면 글자 인식기 — macOS 내장 Vision(VNRecognizeTextRequest · 한국어) 으로 그림 파일 속 글자 상자를 찾는다.
//   s2pipe/화면글자.py 가 처음 부를 때 swiftc 로 한 번 컴파일해 ~/.cache/youstudio/ 에 둔다(설치 없음 — 맥 기본 구성).
//   입력: 표준입력 한 줄에 그림 경로 하나. 출력: 한 줄에 JSON 하나
//     {"f": 경로, "r": [[확신, x, y, w, h, 글자, 왼위x, 왼위y, 오른위x, 오른위y], …]}   (0~1 비율, 원점 = 왼쪽 위)
import AppKit
import Foundation
import Vision

var paths: [String] = []
while let line = readLine() {
    let p = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if !p.isEmpty { paths.append(p) }
}
var out = [String](repeating: "", count: paths.count)
let lock = NSLock()
DispatchQueue.concurrentPerform(iterations: paths.count) { i in
    let path = paths[i]
    var rows: [[Any]] = []
    if let img = NSImage(contentsOfFile: path),
       let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.recognitionLanguages = ["ko-KR", "en-US"]
        req.usesLanguageCorrection = false
        let h = VNImageRequestHandler(cgImage: cg, options: [:])
        do { try h.perform([req]) } catch { FileHandle.standardError.write(("ERR \(error)\n").data(using: .utf8)!) }
        for o in req.results ?? [] {
            guard let c = o.topCandidates(1).first else { continue }
            let b = o.boundingBox
            // 네 모서리(왼위·오른위) — 글줄이 기울었는지(장면 속 글자) 보려고 둔다
            let tl = o.topLeft, tr = o.topRight
            rows.append([Double(c.confidence), Double(b.minX), Double(1 - b.maxY), Double(b.width), Double(b.height), c.string,
                         Double(tl.x), Double(1 - tl.y), Double(tr.x), Double(1 - tr.y)])
        }
    }
    let obj: [String: Any] = ["f": path, "r": rows]
    let data = (try? JSONSerialization.data(withJSONObject: obj, options: [])) ?? Data()
    lock.lock()
    out[i] = String(data: data, encoding: .utf8) ?? "{\"f\":\"\",\"r\":[]}"
    lock.unlock()
}
for s in out { print(s) }
