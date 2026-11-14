from zendilohub.modules.channels.domain.models.email import parse_email, reply_subject, tagged


def mail(subject: str) -> bytes:
    return f'From: carl@customer.example\r\nSubject: {subject}\r\n\r\nHello\r\n'.encode()


def test_finds_the_number_by_the_prefix_and_the_default_one() -> None:
    assert parse_email(mail('Help [Ticket#1001]')).number_tagged('Ticket#') == 1001
    assert parse_email(mail('Help [#1002]')).number_tagged('Ticket#') == 1002
    assert parse_email(mail('Help [#1002] again [ZH-77]')).number_tagged('ZH-') == 77
    assert parse_email(mail('Help [Other#1003]')).number_tagged('Ticket#') is None
    assert parse_email(mail('Help [#1004]')).ticket_number == 1004


def test_reply_subjects_carry_one_tag() -> None:
    assert reply_subject('Re: AW: Printer [#1001]', 1001, 'Ticket#') == 'Re: Printer [Ticket#1001]'
    assert reply_subject('Printer [Ticket#1001]', 1001, 'Ticket#') == 'Re: Printer [Ticket#1001]'
    assert reply_subject('Printer', 7) == 'Re: Printer [#7]'
    assert tagged(5, 'ZH-') == '[ZH-5]'
