from src.coordinates import extract_coordinates


def test_dict_format():
    p = extract_coordinates({'latitude': 30.1, 'longitude': -97.7})
    assert (p.x, p.y) == (-97.7, 30.1)


def test_dict_format_out_of_range_is_rejected():
    assert extract_coordinates({'latitude': 200, 'longitude': -97.7}) is None


def test_dict_format_missing_key():
    assert extract_coordinates({'latitude': 30.1}) is None


def test_degree_string_format():
    p = extract_coordinates("30.1°, -97.7°")
    assert (p.x, p.y) == (-97.7, 30.1)


def test_plain_comma_string_format():
    p = extract_coordinates("30.1, -97.7")
    assert (p.x, p.y) == (-97.7, 30.1)


def test_plain_string_out_of_range_is_rejected():
    assert extract_coordinates("300, -97.7") is None


def test_malformed_string_returns_none():
    assert extract_coordinates("not a coordinate") is None


def test_none_input_returns_none():
    assert extract_coordinates(None) is None


def test_empty_dict_returns_none():
    assert extract_coordinates({}) is None


def test_unsupported_type_returns_none():
    assert extract_coordinates(12345) is None
