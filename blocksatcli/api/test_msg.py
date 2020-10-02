import os, unittest, zlib, shutil
from . import msg
from .gpg import Gpg


class TestApi(unittest.TestCase):
    def test_encapsulation(self):
        """Test custom application-layer encapsulation/decapsulation"""
        # Original message
        data  = bytes([0,1,2,3])

        # ApiMsg on the Tx end (starting from the original data)
        tx_msg = msg.ApiMsg(data)

        # The original data container should be set. The others should be empty.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is None)
        assert(tx_msg.data["encrypted"] is None)

        # Once the data is encapsulated, it is augmented with a header
        expected_len = len(data) + msg.MSG_HEADER_LEN

        # Before the explicit call to the encapsulation function, the data
        # should remain in its original form. Check:
        self.assertTrue(len(tx_msg.get_data()) < expected_len)

        # Encapsulate on user-defined protocol
        tx_msg.encapsulate()

        # Now the encapsulated data container should be non-null too.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is not None)
        assert(tx_msg.data["encrypted"] is None)

        # Get the encapsulated data
        encap_data = tx_msg.get_data()

        # Check that get_data returns the encapsulated data
        self.assertEqual(encap_data, tx_msg.data["encapsulated"])

        # Check that the header was added
        self.assertEqual(len(encap_data), expected_len)

        # ApiMsg on the Rx end (starting from the encapsulated data)
        rx_msg = msg.ApiMsg(encap_data, msg_format="encapsulated")

        # The Rx message starts with only the encapsulated container filled. The
        # other containers are empty.
        assert(rx_msg.data["original"] is None)
        assert(rx_msg.data["encapsulated"] is not None)
        assert(rx_msg.data["encrypted"] is None)

        # Decapsulate (returns True on success)
        self.assertTrue(rx_msg.decapsulate())

        # Now the original data container should be non-null too.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is not None)
        assert(tx_msg.data["encrypted"] is None)

        # Under the hood, decapsulation will check integrity and parse the file
        # name.
        self.assertEqual(tx_msg.filename, rx_msg.filename)

    def test_decapsulation_of_non_encapsulated_data(self):
        """Try to decapsulate a non-encapsulated data object"""
        data   = bytes([0,1,2,3])
        rx_msg = msg.ApiMsg(data, msg_format="encapsulated")

        # The decapsulation should fail
        self.assertFalse(rx_msg.decapsulate())

    def test_msg_len(self):
        """Test encapsulated/encrypted lengths"""
        # Original message
        data  = bytes([0,1,2,3])

        # ApiMsg on the Tx end (starting from the original data)
        tx_msg = msg.ApiMsg(data)

        # Check that the data length returns the original message length
        self.assertEqual(tx_msg.get_length(), len(data))

        # Encapsulate
        tx_msg.encapsulate()

        # Check that the data length returns the encapsulated message length
        self.assertEqual(tx_msg.get_length(), len(data) + msg.MSG_HEADER_LEN)

    def _setup_gpg(self):
        """Setup a test gpg directory"""
        # Setup test gpg directory
        name       = "Test"
        email      = "test@test.com"
        comment    = "comment"
        gpghome    = "/tmp/.gnupg-test"
        passphrase = "test"
        gpg = Gpg(gpghome)
        gpg.create_keys(name, email, comment, passphrase)
        return gpg

    def _teardown_gpg(self):
        """Teardown test gpg directory"""
        gpghome = "/tmp/.gnupg-test"
        # Delete test gpg directory
        shutil.rmtree(gpghome, ignore_errors=True)

    def test_encryption(self):
        """Test encryption/decryption of API message"""
        data = bytes([0,1,2,3])
        gpg  = self._setup_gpg()

        # Message recipient:
        recipient = gpg.get_default_public_key()["fingerprint"]

        # Transmit message
        tx_msg  = msg.ApiMsg(data)

        # The original data container should be set. The others should be empty.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is None)
        assert(tx_msg.data["encrypted"] is None)

        # Encrypt message
        tx_msg.encrypt(gpg, recipient, sign=False, trust=False)

        # Now the encrypted data container should be non-null too.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is None)
        assert(tx_msg.data["encrypted"] is not None)

        cipher_data = tx_msg.get_data()

        # ApiMsg on the Rx end (starting from the encrypted data)
        rx_msg = msg.ApiMsg(cipher_data, msg_format="encrypted")

        # The Rx message starts with only the encrypted container filled. The
        # other containers are empty.
        assert(rx_msg.data["original"] is None)
        assert(rx_msg.data["encapsulated"] is None)
        assert(rx_msg.data["encrypted"] is not None)

        # The gpg module needs the passphrase for decryption (to access the
        # private key). If the passphrase is not provided, and if in
        # non-interactive mode, it should raise RuntimeError. In interactive
        # mode, it would prompt the user for the passphrase.
        with self.assertRaises(RuntimeError):
            rx_msg.decrypt(gpg)

        # Define the passphrase
        passphrase = "test"
        gpg.set_passphrase(passphrase)

        # Decrypt
        self.assertTrue(rx_msg.decrypt(gpg))

        # Now the original data container should be non-null too. Also, because
        # the decryption logic can't detect whether the data is encapsulated, it
        # fills both the original and encapsulated data containers.
        assert(rx_msg.data["original"] is not None)
        assert(rx_msg.data["encapsulated"] is not None)
        assert(rx_msg.data["encrypted"] is not None)

        # Check that the decrypted data matches the original
        self.assertEqual(rx_msg.data['original'], data)

        self._teardown_gpg()

    def test_decryption_of_unencrypted_data(self):
        """Try to decrypt a non-encrypt data object"""
        data = bytes([0,1,2,3])
        gpg  = self._setup_gpg()

        # Transmit message (encrypted)
        tx_msg  = msg.ApiMsg(data)

        # ApiMsg on the Rx end (starting from the supposedly encrypted data,
        # which is actually the non-encrypted data)
        rx_msg = msg.ApiMsg(data, msg_format="encrypted")

        # Define the passphrase
        passphrase = "test"
        gpg.set_passphrase(passphrase)

        # Decrypt should fail
        self.assertFalse(rx_msg.decrypt(gpg))

        self._teardown_gpg()

    def test_encapsulation_and_encryption(self):
        """Test encapsulation+encryption, then decryption+decapsulation"""
        data = bytes([0,1,2,3])
        gpg  = self._setup_gpg()

        # Message recipient:
        recipient = gpg.get_default_public_key()["fingerprint"]

        # Define original message, encapsulate, and encrypt
        tx_msg = msg.ApiMsg(data)
        tx_msg.encapsulate()
        tx_msg.encrypt(gpg, recipient, sign=False, trust=False)

        # All data containers should be non-null at this point.
        assert(tx_msg.data["original"] is not None)
        assert(tx_msg.data["encapsulated"] is not None)
        assert(tx_msg.data["encrypted"] is not None)

        # ApiMsg on the Rx end (starting from the encrypted data)
        rx_msg = msg.ApiMsg(tx_msg.get_data(), msg_format="encrypted")

        # Define the passphrase
        passphrase = "test"
        gpg.set_passphrase(passphrase)

        # Decrypt and decapsulate
        self.assertTrue(rx_msg.decrypt(gpg))
        self.assertTrue(rx_msg.decapsulate())

        # Again, all data containers should be non-null at this point.
        assert(rx_msg.data["original"] is not None)
        assert(rx_msg.data["encapsulated"] is not None)
        assert(rx_msg.data["encrypted"] is not None)

        # Check that the decrypted data matches the original
        self.assertEqual(rx_msg.data['original'], data)

        self._teardown_gpg()

    def test_save(self):
        """Test saving of API msg data"""
        dst_dir = "/tmp/test-api-downloads/"
        data    = bytes([0,1,2,3])

        # Instantiate ApiMsg object and save the data to file
        api_msg = msg.ApiMsg(data)
        api_msg.save(dst_dir)

        # Check the generated file
        dst_file = os.path.join(dst_dir, api_msg.filename)
        with open(dst_file) as fd:
            rd_data = fd.read()
        self.assertEqual(data, rd_data.encode())

        # Clean up
        os.remove(dst_file)

