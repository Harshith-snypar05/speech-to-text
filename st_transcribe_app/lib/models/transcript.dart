/// A saved transcript. Backed by a real .txt file on native platforms, by
/// browser storage (+ a downloaded .txt) on web -- see TranscriptStorage.
class Transcript {
  final String body;
  final DateTime date;

  Transcript({required this.body, required this.date});

  Map<String, dynamic> toJson() => {'body': body, 'date': date.toIso8601String()};

  static Transcript fromJson(Map<String, dynamic> json) =>
      Transcript(body: json['body'] as String, date: DateTime.parse(json['date'] as String));

  String get title {
    final firstLine = body.trim().split('\n').first.trim();
    if (firstLine.isEmpty) return 'Untitled transcript';
    final words = firstLine.split(' ').take(6).join(' ');
    return words.length < firstLine.length ? '$words...' : words;
  }

  String get preview {
    final text = body.trim().replaceAll('\n', ' ');
    return text.length > 60 ? '${text.substring(0, 60)}...' : text;
  }

  String get dateLabel {
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    return '${months[date.month - 1]} ${date.day}, ${date.year}';
  }
}
