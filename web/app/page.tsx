import { prisma } from '@/lib/prisma'
import { ProductCard } from '@/components/ProductCard'
import { Hero } from '@/components/Hero'

export const revalidate = 60

async function getFeaturedProducts() {
  return await prisma.product.findMany({
    where: { featured: true },
    take: 8,
    orderBy: { createdAt: 'desc' },
  })
}

export default async function Home() {
  const featuredProducts = await getFeaturedProducts()

  return (
    <div>
      <Hero />
      
      <section className="container mx-auto px-4 py-16">
        <h2 className="mb-8 text-3xl font-bold">Featured Products</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {featuredProducts.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      </section>
    </div>
  )
}