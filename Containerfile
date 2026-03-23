FROM registry.fedoraproject.org/fedora-minimal:43 AS builder

RUN microdnf install -y python3 python3-pip krb5-devel gcc python3-devel \
    && microdnf clean all

COPY . /app
WORKDIR /app
RUN python3 -m pip install --no-cache-dir --break-system-packages --prefix=/install ".[kerberos]"

FROM registry.fedoraproject.org/fedora-minimal:43

RUN microdnf install -y python3 krb5-workstation krb5-libs \
    && microdnf clean all

COPY --from=builder /install /usr/local

ENTRYPOINT ["mcp-beaker"]
