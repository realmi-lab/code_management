// applefm: Apple 온디바이스 Foundation Model을 JSON 줄 단위로 호출하는 워커.
// 표준 입력에서 한 줄에 요청 하나를 읽고 표준 출력에 한 줄로 응답을 씁니다.
// `--check`를 주면 모델 가용성만 JSON으로 출력하고 끝납니다.
// 요청에 `schema`(JSON Schema 객체)가 있으면 그 구조를 강제해 JSON 문자열을 돌려줍니다.
// 이 프로세스는 네트워크를 열지 않습니다. HTTP 노출은 bridge.py가 맡습니다.
import Foundation
import FoundationModels

struct WorkerUsage: Encodable {
    var prompt_chars: Int
    var completion_chars: Int
}

struct WorkerResponse: Encodable {
    var id: String
    var content: String?
    var error: String?
    var error_type: String?
    var duration_ms: Int
    var usage: WorkerUsage?
}

enum SchemaError: Error, CustomStringConvertible {
    case unsupported(String)
    var description: String {
        switch self {
        case .unsupported(let detail): return "unsupported schema: \(detail)"
        }
    }
}

/// JSON Schema의 부분집합(object/string/number/integer/boolean/array/enum)을 동적 생성 스키마로 바꿉니다.
func dynamicSchema(named name: String, from json: [String: Any]) throws -> DynamicGenerationSchema {
    if let values = json["enum"] as? [String] {
        return DynamicGenerationSchema(name: name, description: json["description"] as? String, anyOf: values)
    }
    guard let type = json["type"] as? String else { throw SchemaError.unsupported("missing type for \(name)") }
    switch type {
    case "object":
        let properties = json["properties"] as? [String: Any] ?? [:]
        let required = Set(json["required"] as? [String] ?? [])
        let order = (json["propertyOrder"] as? [String]) ?? properties.keys.sorted()
        var list: [DynamicGenerationSchema.Property] = []
        for key in order {
            guard let child = properties[key] as? [String: Any] else { continue }
            list.append(DynamicGenerationSchema.Property(
                name: key, description: child["description"] as? String,
                schema: try dynamicSchema(named: key, from: child), isOptional: !required.contains(key)))
        }
        return DynamicGenerationSchema(name: name, description: json["description"] as? String, properties: list)
    case "array":
        guard let items = json["items"] as? [String: Any] else { throw SchemaError.unsupported("array without items: \(name)") }
        return DynamicGenerationSchema(arrayOf: try dynamicSchema(named: name + "Item", from: items),
                                       minimumElements: json["minItems"] as? Int, maximumElements: json["maxItems"] as? Int)
    case "string": return DynamicGenerationSchema(type: String.self)
    case "number": return DynamicGenerationSchema(type: Double.self)
    case "integer": return DynamicGenerationSchema(type: Int.self)
    case "boolean": return DynamicGenerationSchema(type: Bool.self)
    default: throw SchemaError.unsupported("type \(type) for \(name)")
    }
}

@main
struct Main {
    static func availability() -> [String: Any] {
        switch SystemLanguageModel.default.availability {
        case .available:
            return ["available": true]
        case .unavailable(let reason):
            return ["available": false, "reason": String(describing: reason)]
        @unknown default:
            return ["available": false, "reason": "unknown"]
        }
    }

    static func emit(_ object: Any) {
        if let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        }
    }

    static func emit<T: Encodable>(_ value: T) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        if let data = try? encoder.encode(value) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        }
    }

    static func main() async {
        if CommandLine.arguments.contains("--check") {
            emit(availability())
            return
        }
        while let line = readLine(strippingNewline: true) {
            if line.trimmingCharacters(in: .whitespaces).isEmpty { continue }
            let start = Date()
            func elapsed() -> Int { Int(Date().timeIntervalSince(start) * 1000) }
            let object = (try? JSONSerialization.jsonObject(with: Data(line.utf8))) as? [String: Any] ?? [:]
            let id = object["id"] as? String ?? ""
            guard let prompt = object["prompt"] as? String else {
                emit(WorkerResponse(id: id, content: nil, error: "prompt is required", error_type: "bad_request", duration_ms: elapsed(), usage: nil))
                continue
            }
            let system = object["system"] as? String
            do {
                let session: LanguageModelSession
                if let system, !system.isEmpty {
                    session = LanguageModelSession(instructions: system)
                } else {
                    session = LanguageModelSession()
                }
                var options = GenerationOptions()
                if let temperature = object["temperature"] as? Double {
                    if temperature <= 0 {
                        options.sampling = .greedy
                    } else {
                        options.temperature = temperature
                    }
                }
                if let maxTokens = object["max_tokens"] as? Int, maxTokens > 0 {
                    options.maximumResponseTokens = maxTokens
                }
                let content: String
                if let schemaJSON = object["schema"] as? [String: Any] {
                    let root = try dynamicSchema(named: (object["schema_name"] as? String) ?? "Response", from: schemaJSON)
                    let schema = try GenerationSchema(root: root, dependencies: [])
                    let result = try await session.respond(to: prompt, schema: schema, options: options)
                    content = result.content.jsonString
                } else {
                    let result = try await session.respond(to: prompt, options: options)
                    content = result.content
                }
                emit(WorkerResponse(
                    id: id, content: content, error: nil, error_type: nil, duration_ms: elapsed(),
                    usage: WorkerUsage(prompt_chars: (system ?? "").count + prompt.count, completion_chars: content.count)))
            } catch let error as LanguageModelSession.GenerationError {
                emit(WorkerResponse(id: id, content: nil, error: String(describing: error),
                                    error_type: "generation_error", duration_ms: elapsed(), usage: nil))
            } catch {
                emit(WorkerResponse(id: id, content: nil, error: String(describing: error),
                                    error_type: String(describing: type(of: error)), duration_ms: elapsed(), usage: nil))
            }
        }
    }
}
