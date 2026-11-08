"""Small policy adapters around pinned upstream Presidio recognizers."""
import re


def add_contextual_recognizers(analyzer, policy):
    from presidio_analyzer import Pattern, PatternRecognizer
    from presidio_analyzer.predefined_recognizers import CreditCardRecognizer, UsPassportRecognizer, IbanRecognizer
    upstream={'CreditCardRecognizer':CreditCardRecognizer,'UsPassportRecognizer':UsPassportRecognizer,'IbanRecognizer':IbanRecognizer}
    for spec in policy['text'].get('contextual_recognizers',[]):
        source=upstream[spec['upstream']]
        patterns=[]
        for pattern in source.PATTERNS:
            # Upstream \b excludes digit sequences adjacent to Chinese prose.
            # Keep the mature number syntax, requiring surrounding context for
            # this weaker, non-checksum privacy candidate to pass the threshold.
            regex=pattern.regex
            if regex.startswith(r'\b'):regex=r'(?<!\d)'+regex[2:]
            if regex.endswith(r'\b'):regex=regex[:-2]+r'(?!\d)'
            patterns.append(Pattern(pattern.name,regex,spec['base_score']))
        for language,context in spec['context_by_language'].items():
            localized=list(patterns)
            labels=spec.get('explicit_labels_by_language',{}).get(language,[])
            if labels:
                prefix=r'(?i)(?<=(?<![A-Za-z0-9_])(?:'+'|'.join(re.escape(label) for label in labels)+r')\s*[:=：]\s*)'
                localized.extend(Pattern(pattern.name+'-field',prefix+pattern.regex,0.9) for pattern in patterns)
            analyzer.registry.add_recognizer(PatternRecognizer(
                name=spec['name']+'-'+language,supported_language=language,
                supported_entity=spec['entity'],patterns=localized,context=context))
