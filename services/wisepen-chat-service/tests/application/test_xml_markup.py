from chat.application.utils.xml_markup import xml_attr, xml_cdata, xml_text


def test_xml_cdata_splits_embedded_cdata_close_marker() -> None:
    assert xml_cdata("before ]]> after") == "<![CDATA[before ]]]]><![CDATA[> after]]>"


def test_xml_attr_escapes_double_quotes_and_xml_special_chars() -> None:
    assert xml_attr('a "quoted" & <tag>') == "a &quot;quoted&quot; &amp; &lt;tag&gt;"


def test_xml_text_escapes_xml_special_chars() -> None:
    assert xml_text("a & <tag>") == "a &amp; &lt;tag&gt;"
