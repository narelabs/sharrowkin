import Link from 'next/link'

export function Hero() {
  return (
    <section className="bg-gradient-to-r from-primary-600 to-primary-800 text-white">
      <div className="container mx-auto px-4 py-24 text-center">
        <h1 className="mb-6 text-5xl font-bold">
          Welcome to Sharrowkin Marketplace
        </h1>
        <p className="mb-8 text-xl">
          Discover amazing products at unbeatable prices
        </p>
        <Link
          href="/products"
          className="inline-block rounded-lg bg-white px-8 py-3 font-semibold text-primary-600 transition hover:bg-gray-100"
        >
          Shop Now
        </Link>
      </div>
    </section>
  )
}