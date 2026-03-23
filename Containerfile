FROM registry.fedoraproject.org/fedora-minimal:43

RUN microdnf install -y python3 python3-pip krb5-devel krb5-workstation gcc python3-devel \
    && microdnf clean all

COPY . /app
WORKDIR /app

RUN python3 -m pip install --no-cache-dir --break-system-packages ".[kerberos]"

ENTRYPOINT ["mcp-beaker"]
