
import sqlalchemy
from sqlalchemy.sql import text

import os
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format=f'%(asctime)s.%(msecs)03d - {os.getpid()} - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)


class Ledger:
    '''
    Python interface to the ledger database.

    Each operation uses a database connection from the engine.
    Write operations execute inside explicit transactions.
    '''

    def __init__(self, url):
        self.engine = sqlalchemy.create_engine(url)

    def get_all_account_ids(self):
        '''
        Return all account IDs.

        Used by random_transfers.py.
        '''
        sql = text('SELECT account_id FROM accounts;')
        logging.debug(sql)

        with self.engine.connect() as conn:
            results = conn.execute(sql)
            return [row[0] for row in results.all()]

    def create_account(self, name):
        '''
        Create an account and initialize its balance to zero.

        Both INSERT statements execute atomically.
        '''
        with self.engine.begin() as conn:

            # Insert the account and retrieve its generated ID.
            sql = text("""
                INSERT INTO accounts (name)
                VALUES (:name)
                RETURNING account_id;
            """)
            logging.debug(sql)

            result = conn.execute(sql, {"name": name})
            account_id = result.scalar_one()

            # Initialize the balance.
            sql = text("""
                INSERT INTO balances (account_id, balance)
                VALUES (:account_id, 0);
            """)
            logging.debug(sql)

            conn.execute(sql, {"account_id": account_id})

    def transfer_funds(
            self,
            debit_account_id,
            credit_account_id,
            amount
            ):
        '''
        Transfer funds atomically between two accounts.

        Row-level locks prevent concurrent lost updates.
        A consistent lock order reduces deadlock risk.

        The transaction is committed on success and
        rolled back automatically on failure.
        '''
        with self.engine.begin() as conn:
            # Task 3: serialize transfers by locking the balances table.
            # sql = text('LOCK TABLE balances IN ACCESS EXCLUSIVE MODE;')
            # logging.debug(sql)
            # conn.execute(sql)

            # Lock both accounts in a deterministic order.
            # This prevents concurrent transfers from
            # modifying the same balances simultaneously.
            sql = text("""
                SELECT account_id
                FROM balances
                WHERE account_id IN (:debit_id, :credit_id)
                ORDER BY account_id
                FOR UPDATE;
            """)
            logging.debug(sql)

            result = conn.execute(
                sql,
                {
                    "debit_id": debit_account_id,
                    "credit_id": credit_account_id,
                },
            )

            locked_ids = {row[0] for row in result.all()}

            if locked_ids != {debit_account_id, credit_account_id}:
                raise ValueError("One or more accounts do not exist.")

            # Record the transfer.
            sql = text("""
                INSERT INTO transactions
                    (debit_account_id, credit_account_id, amount)
                VALUES
                    (:debit_account_id, :credit_account_id, :amount);
            """)
            logging.debug(sql)

            conn.execute(
                sql,
                {
                    "debit_account_id": debit_account_id,
                    "credit_account_id": credit_account_id,
                    "amount": amount,
                },
            )

            # Debit the source account.
            # Update directly in SQL to avoid lost updates.
            sql = text("""
                UPDATE balances
                SET balance = balance - :amount
                WHERE account_id = :account_id;
            """)
            logging.debug(sql)

            conn.execute(
                sql,
                {
                    "account_id": debit_account_id,
                    "amount": amount,
                },
            )

            # Credit the destination account.
            sql = text("""
                UPDATE balances
                SET balance = balance + :amount
                WHERE account_id = :account_id;
            """)
            logging.debug(sql)

            conn.execute(
                sql,
                {
                    "account_id": credit_account_id,
                    "amount": amount,
                },
            )
