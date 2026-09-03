def make_ofx(
    *transactions: str,
    xml: bool = True,
    bank: str = "001",
    account: str = "1234",
) -> bytes:
    body = "".join(f"<STMTTRN>{transaction}</STMTTRN>" for transaction in transactions)
    leaf = (
        (lambda tag, value: f"<{tag}>{value}</{tag}>")
        if xml
        else (lambda tag, value: f"<{tag}>{value}\n")
    )
    document = (
        "OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nENCODING:USASCII\nCHARSET:1252\n\n"
        "<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>"
        f"<CURDEF>BRL{'</CURDEF>' if xml else ''}"
        "<BANKACCTFROM>"
        f"{leaf('BANKID', bank)}{leaf('BRANCHID', '0001')}{leaf('ACCTID', account)}"
        "</BANKACCTFROM><BANKTRANLIST>"
        f"{body}</BANKTRANLIST><LEDGERBAL>{leaf('BALAMT', '1200.00')}"
        "</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    )
    return document.encode("cp1252")


def tx_xml(date: str, amount: str, fitid: str, memo: str) -> str:
    return (
        f"<TRNTYPE>OTHER</TRNTYPE><DTPOSTED>{date}</DTPOSTED>"
        f"<TRNAMT>{amount}</TRNAMT><FITID>{fitid}</FITID><MEMO>{memo}</MEMO>"
    )


def tx_sgml(date: str, amount: str, fitid: str, memo: str) -> str:
    return f"<TRNTYPE>OTHER\n<DTPOSTED>{date}\n<TRNAMT>{amount}\n<FITID>{fitid}\n<MEMO>{memo}\n"


def canonical_csv(*rows: str) -> bytes:
    header = (
        "transaction_date,account,description,amount,balance_after,nature,category,"
        "subcategory,is_internal_transfer,is_extraordinary,source_file,source_row,confidence\n"
    )
    return (header + "\n".join(rows) + "\n").encode()
